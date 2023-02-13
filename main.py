import asyncio
import os
import re
import sqlite3
from pprint import pformat

import interactions
from dotenv import load_dotenv
from interactions import Client, ClientPresence, PresenceActivity, PresenceActivityType, Intents, Message, \
    MessageReaction, get, Embed, EmbedFooter, EmbedAuthor, CommandContext, OptionType, Permissions, Member, Role, Guild, \
    Button, ButtonStyle, ComponentContext, Emoji

from constants import FLAG_DATA_REGIONAL
from translate import translate_text, translation_tostring, detect_text_language, get_language_name


def main():
    # region Start Bot
    load_dotenv('.env')
    token = os.getenv('DISCORD_TOKEN')
    conn = sqlite3.connect("database.db")

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
        print(reaction)

        # emoji they reacted with
        emoji = reaction.emoji.name
        print(emoji)

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
            "color": 0x56b0fd
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

    @translate_command.subcommand(
        name='settings',
    )
    async def settings_command(ctx: CommandContext):
        """ Update your server's translation settings """
        await ctx.send('settings command')

    @client.command(
        name='tban',
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
            "color": 0x56b0fd,
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
                                    custom_id='reset_perms_ban')

        embed = Embed(**embed_dict)
        message = await ctx.send(embeds=embed, components=button, ephemeral=True)
        if not button:  # if the doesn't exist, no need to wait for component
            return
        if not ban_role:  # if the role doesn't exist, something went wrong, disable component and return
            await message.disable_all_components()
            return
        try:
            button_ctx: ComponentContext = await client.wait_for_component(button, message, timeout=30)
            print(pformat(button_ctx))
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

    client.start()


if __name__ == '__main__':
    main()
