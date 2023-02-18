import asyncio
import os
import re
import sqlite3
from pprint import pformat
from functools import partial

import interactions
from dotenv import load_dotenv
from interactions import Client, ClientPresence, PresenceActivity, PresenceActivityType, Intents, Message, \
    MessageReaction, get, Embed, EmbedFooter, EmbedAuthor, CommandContext, OptionType, Permissions, Member, Role, Guild, \
    Button, ButtonStyle, ComponentContext, Emoji, EmbedField, ActionRow, EmbedImageStruct, spread_to_rows, Component, \
    SelectMenu, SelectOption, ComponentType, ChannelType

from constants import FLAG_DATA_REGIONAL
from translate import translate_text, translation_tostring, detect_text_language, get_language_name
from utils import EMBED_COLOUR


def main():
    # region Start Bot
    load_dotenv('.env')
    token = os.getenv('DISCORD_TOKEN')
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    presence = ClientPresence(
        activities=[
            PresenceActivity(
                type=PresenceActivityType.WATCHING, name="for language barriers!"
            )
        ]
    )

    client = Client(
        token=token,
        intents=Intents.DEFAULT | Intents.GUILD_MESSAGE_CONTENT,
        presence=presence,
        default_scope=871132162261397534  # TODO remove when going live
    )

    @client.event
    async def on_start():
        print("Bot has been launched successfully.")

    # endregion

    # region Flag Reactions
    async def should_process(reaction: MessageReaction, message: Message, emoji: str):
        if reaction.member.bot:  # reaction was made by a bot
            return False
        if emoji not in FLAG_DATA_REGIONAL and emoji != '🌐':
            return False
        return True

    @client.event()
    async def on_message_reaction_add(reaction: MessageReaction):
        emoji = reaction.emoji.name  # emoji they reacted with

        # message they reacted to
        message: Message = await get(
            client, Message,
            parent_id=int(reaction.channel_id),
            object_id=int(reaction.message_id)
        )

        if not await should_process(reaction, message, emoji):
            return

        try:
            referenced_message: Message = await get(
                client, Message,
                parent_id=int(reaction.channel_id),
                object_id=message._json["referenced_message"]["id"]  # required workaround
            )
            # update translated message to the original message if reaction on translation message
            message = referenced_message if client.me.id == message.author.id else message

        except (TypeError, KeyError):
            pass
        embed_dict: dict = {
            "color": EMBED_COLOUR
        }
        if emoji == '🌐':  # language detection
            result = await detect_text_language(message.content)
            confidence = result['confidence'] * 100
            confidence_percent = f'{int(confidence)}%'
            detection_text = "Something went wrong during detection. Contact an admin"
            if confidence <= 0:
                detection_text = 'Not sure what language that is. Sorry!'
            elif confidence <= 70:
                detection_text = f'I am only {confidence_percent} sure the language is {result["language"]}'
            elif confidence <= 100:
                detection_text = f'This text is in `{result["language"]}`'

            embed_dict['description'] = detection_text
            embed_dict['footer'] = EmbedFooter(text=f'{reaction.member.name} ・ {confidence_percent} Confident')

        else:  # text translation
            translation_data = await translate_text(
                FLAG_DATA_REGIONAL[emoji],  # target languages
                message.content  # text to translate
            )
            translated_text = await translation_tostring(translation_data)

            embed_dict['author'] = EmbedAuthor(name=reaction.member.name)
            embed_dict['description'] = translated_text
            embed_dict['footer'] = EmbedFooter(
                text=f'From {await get_language_name(translation_data[0]["detectedSourceLanguage"])} ・ '
                     f'by {reaction.member.name}'
            )

        embed = Embed(**embed_dict)
        await message.reply(embeds=[embed])

    # endregion

    # region Commands
    @client.command(name='t')
    async def translate_command(ctx: CommandContext):
        pass

    @translate_command.subcommand(name='text')
    @interactions.option(description='Text to translate', required=True)
    @interactions.option(description='Target languages', required=True)
    async def text_command(ctx: CommandContext, text: str = None, languages: str = None):
        await ctx.send(f"You selected the command_name sub command and put in {text} and "
                       f"{re.findall('[a-z]{2}', languages)}")

    @client.command(name='admin', default_member_permissions=Permissions.ADMINISTRATOR, )
    async def admin(ctx: CommandContext):
        """ Configurate your server's translation settings """

        def update_guild_data() -> dict:
            """ Returns updated guild data from the database """
            cursor.execute("SELECT * FROM guild WHERE id = ?", [int(ctx.guild_id)])
            return dict(cursor.fetchone())

        def update_auto_delete_options(settings_data: dict) -> [SelectOption]:
            cd = settings_data['auto_delete_cd']
            options = [
                SelectOption(label=label, value=seconds, description=f'Delete translation messages after {label}',
                             emoji=Emoji(name='⌛'), default=True if cd == seconds else False)
                for label, seconds in [
                    ('30 Seconds', 30),
                    ('1 Minute', 60),
                    ('2 Minutes', 120),
                    ('5 Minutes', 300),
                    ('15 Minutes', 900)
                ]
            ]
            options.insert(
                0, SelectOption(label='Never delete', value=-1, description='Never delete translation messages',
                                emoji=Emoji(name='⌛'), default=True if not cd else False)
            )
            for option in options:
                print(option)
            return options

        guild_data = update_guild_data()
        footer = EmbedFooter(text='disclate ・ v1.0')
        guild = await ctx.get_guild()

        async def create_home_embed() -> (Embed, [ActionRow], [Component]):
            embed_dict = {
                'title': f'`{guild.name}`',
                'thumbnail': EmbedImageStruct(url=guild.icon_url),
                'description': 'This is the `Admin Panel`, use the buttons below to configure your server.',
                'fields': [
                    EmbedField(name=f'Tokens',
                               value=guild_data['tokens'], inline=True),
                    EmbedField(name='Characters Translated', value=guild_data['characters_translated'],
                               inline=True)
                ],
                'color': EMBED_COLOUR,
                'footer': footer
            }
            embed = Embed(**embed_dict)

            # todo linked channels button
            labels = ['server', 'categories', 'channels']
            settings_buttons = [
                Button(style=ButtonStyle.SECONDARY, label=label.title(), custom_id=f'{label}_settings',
                       emoji=Emoji(id='1075539703014633512')) for label in labels]

            shop_button = Button(style=ButtonStyle.LINK, label='Buy Tokens', url='https://www.google.com/',
                                 emoji=Emoji(id='1075540183941914788'))
            support_button = Button(style=ButtonStyle.SECONDARY,
                                    label='Support', custom_id='support', emoji=Emoji(id='1075539728553750621'))
            rows = [
                ActionRow(components=settings_buttons),
                ActionRow(components=[shop_button, support_button])
            ]
            return embed, rows, [*settings_buttons, shop_button, support_button]

        async def create_server_settings_embed() -> (Embed, [ActionRow], [Component]):
            flag_t = guild_data['flag_translation']
            cmd_t = guild_data['command_translation']
            
            embed_dict = {
                'title': f'`{guild.name}` - Server Settings',
                'thumbnail': EmbedImageStruct(url=guild.icon_url),
                'description': 'This is the `Server Settings` page, changes here affect the *whole* server. '
                               '\n\nSettings on this page:\n'
                               '`Auto Delete` Dropdown for translation message lifetime.\n'
                               '`Flag/Command Translation` Buttons to toggle flag/command translations',
                'fields': [
                    EmbedField(name=f'Flag Translation', value='Active' if flag_t else 'Not active', inline=True),
                    EmbedField(name='Command Translation', value='Active' if cmd_t else 'Not active', inline=True)
                ],
                'color': EMBED_COLOUR,
                'footer': footer
            }
            embed = Embed(**embed_dict)
            print(F'AUTO DELETE OPTIONS: {auto_delete_options}')
            auto_delete_select = SelectMenu(
                custom_id='auto_delete_guild',
                options=auto_delete_options
            )
            back_button = Button(style=ButtonStyle.SECONDARY,
                                 label='Back', custom_id='to_homepage', emoji=Emoji(id='1075538962787082250'))
            flag_button = Button(style=ButtonStyle.SUCCESS if flag_t else ButtonStyle.DANGER, label='Flag Translation',
                                 custom_id='flag_toggle', emoji=Emoji(name='🇨🇦'))
            cmd_button = Button(style=ButtonStyle.SUCCESS if cmd_t else ButtonStyle.DANGER, label='Command Translation',
                                custom_id='command_toggle', emoji=Emoji(id='1075542290698866759'))
            rows = spread_to_rows(auto_delete_select, back_button, flag_button, cmd_button)
            return embed, rows, [auto_delete_select, back_button, flag_button, cmd_button]

        async def create_category_settings_embed() -> (Embed, [ActionRow], [Component]):
            embed_dict = {
                'title': f'`{guild.name}` - Category Settings',
                'thumbnail': EmbedImageStruct(url=guild.icon_url),
                'description': f'This is the `Category Settings` page, you can make changes here that '
                               f'affect a categories and all the channels under it. '
                               f'\n\nChoose a category from the dropdown to view its configuration.',
                'color': EMBED_COLOUR,
                'footer': footer
            }
            if selected_category:
                embed_dict['fields'] = [
                    EmbedField(name=f'Auto Translation', value='> English, French, Afrikaans, Latin', inline=True),
                    EmbedField(name='Auto Delete', value='> Inherit', inline=True),
                    EmbedField(name='Channels Affected', value='> #mytesting\n> #dump\n> #review', inline=True)
                ]
            embed = Embed(**embed_dict)
            back_button = Button(style=ButtonStyle.SECONDARY,
                                 label='Back', custom_id='to_homepage', emoji=Emoji(id='1075538962787082250'))
            edit_button = Button(style=ButtonStyle.PRIMARY,
                                 label='Edit', custom_id='edit_category_settings', emoji=Emoji(name='✏️'))
            category_select = SelectMenu(
                custom_id='category_select',
                type=ComponentType.CHANNEL_SELECT,
                channel_types=[ChannelType.GUILD_CATEGORY]
            )
            rows = spread_to_rows(category_select, back_button, edit_button)
            return embed, rows, [category_select, back_button, edit_button]

        async def create_channel_settings_embed() -> (Embed, [ActionRow], [Component]):
            embed_dict = {
                'title': f'`{guild.name}` - Channel Settings',
                'thumbnail': EmbedImageStruct(url=guild.icon_url),
                'description': f'This is the `Category Settings` page, you can make changes here that '
                               f'affect a categories and all the channels inside it. '
                               f'\n\nChoose a category from the dropdown to view its configuration.',
                'color': EMBED_COLOUR,
                'footer': footer
            }

            if selected_channel:
                embed_dict['fields'] = [
                    EmbedField(name=f'Auto Translation', value='> English, French, Afrikaans, Latin', inline=True),
                    EmbedField(name='Auto Delete', value='> Inherit', inline=True)
                ]
            embed = Embed(**embed_dict)
            back_button = Button(style=ButtonStyle.SECONDARY,
                                 label='Back', custom_id='to_homepage', emoji=Emoji(id='1075538962787082250'))
            edit_button = Button(style=ButtonStyle.PRIMARY,
                                 label='Edit', custom_id='edit_channel_settings', emoji=Emoji(name='✏️'))
            channel_select = SelectMenu(
                custom_id='channel_select',
                type=ComponentType.CHANNEL_SELECT,
                channel_types=[ChannelType.GUILD_TEXT]
            )
            rows = spread_to_rows(channel_select, back_button, edit_button)
            return embed, rows, [channel_select, back_button, edit_button]

        next_embed, action_rows, all_components = await create_home_embed()
        message = await ctx.send(embeds=next_embed, components=action_rows)

        async def component_check(check_ctx: ComponentContext):
            if check_ctx.member.id != ctx.member.id:
                return False
            return True

        while True:
            try:
                button_ctx: ComponentContext = await client.wait_for_component(
                    all_components, message, check=component_check, timeout=120)
                custom_id = button_ctx.custom_id
                print(f'Button pressed: {custom_id}')
                match custom_id:
                    # region Homepage
                    case 'to_homepage':
                        guild_data = update_guild_data()
                        next_embed_function = create_home_embed
                    case 'server_settings':
                        guild_data = update_guild_data()
                        auto_delete_options = update_auto_delete_options(guild_data)
                        next_embed_function = create_server_settings_embed
                    case 'categories_settings':
                        selected_category = None
                        next_embed_function = create_category_settings_embed
                    case 'channels_settings':
                        selected_channel = None
                        print('here')
                        next_embed_function = create_channel_settings_embed
                    # endregion
                    # region Server Settings
                    case 'flag_toggle' | 'command_toggle':
                        if custom_id == 'flag_toggle':
                            col = 'flag_translation'
                        else:
                            col = 'command_translation'
                        new_value = not bool(guild_data[col])
                        cursor.execute(f"UPDATE guild SET {col}=? WHERE id=?;",
                                       (new_value, int(guild.id)))
                        conn.commit()
                        guild_data = update_guild_data()
                        next_embed_function = create_server_settings_embed
                    case 'auto_delete_guild':
                        new_cooldown = int(button_ctx.data.values[0])
                        if new_cooldown == -1:
                            new_cooldown = None
                            print(new_cooldown)

                        cursor.execute(f"UPDATE guild SET auto_delete_cd=? WHERE id=?;", (new_cooldown, int(guild.id)))
                        next_embed_function = create_server_settings_embed
                        conn.commit()
                        guild_data = update_guild_data()
                        auto_delete_options = update_auto_delete_options(guild_data)
                    # endregion
                    # region Category Settings

                    case 'category_select':
                        selected_category = button_ctx.data.values[0]
                        next_embed_function = create_category_settings_embed
                    # endregion
                    # region Channel Settings
                    case 'channel_select':
                        selected_channel = button_ctx.data.values[0]
                        next_embed_function = create_channel_settings_embed

                    # endregion
                    case other:
                        print('ERROR: Invalid custom_id value: ' + other)
                        raise asyncio.TimeoutError
                next_embed, action_rows, all_components = await next_embed_function()
                message = await button_ctx.edit(embeds=next_embed, components=action_rows)

            except asyncio.TimeoutError:
                await message.edit(embeds=Embed(
                    description=f'Your session has expired, please use `/{ctx.data.name}` again if you would '
                                f'like to continue.'))
                break

    @client.command(
        name='ban',
        default_member_permissions=Permissions.ADMINISTRATOR,
    )
    @interactions.option(
        type=OptionType.USER,
        description='User to ban from using translate features',
        required=True
    )
    async def ban_command(ctx: CommandContext, member: Member):
        """ Ban a user from using the bot """

        # todo create role if missing
        #  https://interactionspy.readthedocs.io/en/latest/api.models.guild.html#interactions.api.models.guild.Guild.create_role
        ban_role_name = 'no-translate'
        guild: Guild = await ctx.get_guild()
        roles: [Role] = await guild.get_all_roles()
        print(pformat(roles))
        embed_dict: dict = {
            "color": EMBED_COLOUR,
            "description": ""
        }

        role_names = [role.name for role in roles]
        # if the role does not exist yet, create it
        if ban_role_name not in role_names:
            await guild.create_role(
                ban_role_name,
                0,
                reason=f'The {ban_role_name} was created to assign to users that are banned from using '
                       f'translation features.'
            )
            embed_dict['description'] += f'❗NOTICE: A `{ban_role_name}` role was created.\n\n'
        button, ban_role = None, None
        for role in roles:
            if role.name == ban_role_name:
                ban_role = role
                if ban_role.id in member.roles:
                    await guild.remove_member_role(ban_role.id, member.id,
                                                   reason="Unbanned user from using translations.")
                    embed_dict['title'] = f'Unbanned user `{member.name}`'
                    embed_dict['description'] += f'> Removed `{ban_role_name}` role from {member.mention}'
                else:
                    await guild.add_member_role(ban_role.id, member.id, reason="Banned user from using translations.")
                    embed_dict['title'] = f'Banned user `{member.name}`'
                    embed_dict['description'] += f'> Added `{ban_role_name}` role to {member.mention}'

                # warn about any existing translation role perms
                if ban_role.permissions != 0:
                    embed_dict['description'] += (f'\n\n**⚠️ WARNING:** `The {ban_role_name} role currently grants '
                                                  f'permissions! Use the button below or '
                                                  f'update in ⚙️ Server Settings`')
                    button = Button(style=ButtonStyle.DANGER, label=f'Remove `{ban_role_name}` permissions',
                                    custom_id='reset_perms')

        embed = Embed(**embed_dict)
        message = await ctx.send(embeds=embed, components=button, ephemeral=True)
        if not button:  # if the doesn't exist, no need to wait for component
            return
        if not ban_role:  # if the role doesn't exist, something went wrong, disable component and return
            await message.disable_all_components()
            return
        try:
            button_ctx: ComponentContext = await client.wait_for_component(button, message, timeout=30)
            if button_ctx.custom_id == 'reset_perms_ban':
                reason = f'Removed potentially unsafe permissions attached to the `{ban_role_name}` role.'
                await guild.modify_role(ban_role.id, permissions=0, reason=reason)
                success_button = Button(style=ButtonStyle.SUCCESS, emoji=Emoji(name='✅'),
                                        label='Success', custom_id='success', disabled=True)
                await button_ctx.edit(components=success_button)  # reply with success
        except asyncio.exceptions.TimeoutError:
            pass

    # endregion
    # region Listeners

    @client.event()
    async def on_component(ctx: ComponentContext):
        pass

    # endregion

    client.start()  # start discord client

    # close cursor and database connection
    cursor.close()
    conn.close()


if __name__ == '__main__':
    main()
