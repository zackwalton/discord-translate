import asyncio
import os
import re
import sqlite3
from pprint import pformat

import interactions
from dotenv import load_dotenv
from interactions import Client, ClientPresence, PresenceActivity, PresenceActivityType, Intents, Message, \
    MessageReaction, get, Embed, EmbedAuthor, CommandContext, OptionType, Permissions, Member, Role, \
    Guild, Button, ButtonStyle, ComponentContext, Emoji, EmbedField, ActionRow, EmbedImageStruct, spread_to_rows, \
    Component, SelectMenu, SelectOption, ComponentType, ChannelType, Thread

from const import FLAG_DATA_REGIONAL
from translate import translate_text, translation_tostring, detect_text_language
from utils import *


def main():
    # region Start Bot
    load_dotenv('.env')
    token = os.getenv('DISCORD_TOKEN')

    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('PRAGMA foreign_keys = ON')  # enable foreign key constraints

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

    async def should_process(message: Message, reaction: MessageReaction = None):
        if reaction:
            emoji = reaction.emoji.name  # emoji they reacted with
            if reaction.member.bot:  # reaction was made by a bot
                return False
            if emoji not in FLAG_DATA_REGIONAL and emoji != '🌐':
                return False
        else:  # no reaction on message
            if message.author.id == client.me.id:  # message was sent by the bot
                return False
        if not message.content:  # message has no content todo check for embed text
            return False

        return True

    # region Flag Reactions

    @client.event()
    async def on_message_reaction_add(reaction: MessageReaction):
        emoji = reaction.emoji.name  # emoji they reacted with

        # message they reacted to
        message: Message = await get(
            client, Message,
            parent_id=int(reaction.channel_id),
            object_id=int(reaction.message_id)
        )

        if not await should_process(message, reaction=reaction):
            return

        try:
            # noinspection PyProtectedMember
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
                detection_text = f'This text is in `{get_language_name(result["language"], add_native=True)}`'

            embed_dict['description'] = detection_text
            embed_dict['footer'] = EmbedFooter(text=f'{reaction.member.name} ・ {confidence_percent} Confident')

        else:  # text translation
            translation_data = await translate_text(
                FLAG_DATA_REGIONAL[emoji],  # target languages
                message.content  # text to translate
            )
            if not translation_data:
                return
            translated_text = await translation_tostring(translation_data)

            embed_dict['author'] = EmbedAuthor(name=reaction.member.name)
            embed_dict['description'] = translated_text
            if 'detectedSourceLanguage' in translation_data[0]:
                from_lang = f'{get_language_name(translation_data[0]["detectedSourceLanguage"], native_only=True)} → '
            else:
                from_lang = ''
            to_lang = f'{", ".join([get_language_name(e, native_only=True) for e in FLAG_DATA_REGIONAL[emoji]])}'
            embed_dict['footer'] = EmbedFooter(
                text=f'{from_lang}{to_lang} ・ for {reaction.member.name}'
            )

        embed = Embed(**embed_dict)
        await message.reply(embeds=[embed])

    # endregion

    # region Message Events
    @client.event()
    async def on_message_create(message: Message):
        if not await should_process(message):
            return
        channel_id = message.channel_id
        channel: Channel = await get(client, Channel, object_id=int(channel_id))
        match channel.type:
            # region Text Channel Message Event
            case ChannelType.GUILD_TEXT:  # message sent in a text channel
                print(f'DEBUG: Message sent in text channel `{channel.name}` ({channel.id})')
                links = cursor.execute('SELECT * FROM channel_link WHERE channel_from_id = ?;', (str(channel_id),))
                links = [dict(link) for link in links.fetchall()]
                if not links:
                    return

                for link_data in links:
                    # for channel in link_data['channels']:
                    #     pass
                    embed_dict: dict = {
                        "color": EMBED_COLOUR,
                        "author": EmbedAuthor(name=message.member.name),  # todo add avatar url
                    }
                    translation_data = await translate_text(
                        [],  # target languages
                        message.content  # text to translate
                    )
                    channel_to_id = link_data['channel_to_id']
                    channel_to: Channel = await get(client, Channel, object_id=int(channel_to_id))
                    if channel_to.type == ChannelType.GUILD_TEXT:
                        print(message.content)
                        await channel_to.send(message.content)
                # endregion

            # region Thread Message Event
            case ChannelType.GUILD_FORUM | ChannelType.PUBLIC_THREAD | ChannelType.PRIVATE_THREAD:  # message sent in a guild forum text_channel
                print(f'DEBUG: Message sent in thread `{channel.name}` ({channel.id})')

    # endregion

    # region Thread Events

    async def create_thread_select_menu(selected: [] = None):
        selected = selected if selected else []
        return SelectMenu(
            custom_id='thread_auto_translation',
            placeholder='Select languages for auto-translation...',
            min_values=0,
            max_values=2,
            options=[
                SelectOption(label='English', value='en', emoji=Emoji(name='🇬🇧'), default='en' in selected),
                SelectOption(label='German', value='de', emoji=Emoji(name='🇩🇪'), default='de' in selected),
                SelectOption(label='French', value='fr', emoji=Emoji(name='🇫🇷'), default='fr' in selected),
                SelectOption(label='Spanish', value='es', emoji=Emoji(name='🇪🇸'), default='es' in selected),
            ]
        )

    thread_translation_message = 'Choose auto-translation languages for messages in this thread!'

    @client.event()
    async def on_thread_create(thread: Thread):
        if not thread.newly_created:
            return
        print(f'DEBUG: Thread created, id: {thread.id}')
        select_menu = await create_thread_select_menu()
        await asyncio.sleep(0.5)  # wait for thread to be created and first message to send
        try:
            message = await thread.send(thread_translation_message, components=spread_to_rows(select_menu))
        except interactions.LibraryException:  # avoid exception raised when send is too fast
            await asyncio.sleep(5)
            message = await thread.send(thread_translation_message, components=spread_to_rows(select_menu))

        await message.pin()  # pin the message in the thread

    @client.component('thread_auto_translation')
    async def thread_auto_translation(ctx: ComponentContext, values: [] = None):
        if ctx.author.id != ctx.channel.owner_id:
            has_perms = await ctx.author.has_permissions(
                Permissions.MANAGE_THREADS,
                Permissions.MANAGE_CHANNELS,
                Permissions.ADMINISTRATOR,
                channel=ctx.channel,
                guild_id=ctx.guild.id,
                operator="or")
            if not has_perms:
                await ctx.send('❌ Only the thread owner and server admins can change the '
                               'auto-translation settings for this thread!', ephemeral=True)
                return
        print('DEBUG: Thread auto translation languages: ', values)
        select_menu = await create_thread_select_menu(values)
        await ctx.edit(thread_translation_message, components=select_menu)
        if values:
            cursor.execute('REPLACE INTO thread VALUES (?, ?, ?);',
                           (str(ctx.channel.id), json.dumps(values), db_timestamp()))
        else:
            cursor.execute('DELETE FROM thread WHERE thread_id = ?;', (str(ctx.channel.id),))
        conn.commit()

    # endregion

    # region Commands
    @client.command(name='t')
    async def translate_command(_: CommandContext):
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
        guild: Guild = await ctx.get_guild()

        def update_guild_data() -> dict:
            """ Returns updated guild data from the database """
            cursor.execute("SELECT * FROM guild WHERE id = ?", [int(guild.id)])
            return dict(cursor.fetchone())

        async def update_category_data() -> [dict]:
            """ Returns updated category data from the database """
            print(f'DEBUG: Updating category data for {selected_category}')
            cursor.execute(f"SELECT * FROM category WHERE id = (?)", (selected_category,))
            query = cursor.fetchone()
            if query:
                return dict(query)
            else:
                print('DEBUG: Did not find the category, creating entry.')
                cursor.execute(f"INSERT INTO category (id) VALUES (?)", (selected_category,))
                return await update_category_data()

        async def update_channel_data() -> [dict]:
            """ Returns updated channel data from the database """
            print(f'DEBUG: Updating channel data for {selected_channel}')
            cursor.execute(f"SELECT * FROM channel WHERE id = (?)", (selected_channel,))
            query = cursor.fetchone()
            if query:
                return dict(query)
            else:
                print('DEBUG: Did not find the channel, creating entry.')
                cursor.execute(f"INSERT INTO channel (id) VALUES (?)", (selected_channel,))
                return await update_channel_data()

        def update_auto_delete_options(settings_data: dict) -> [SelectOption]:
            print(f'DEBUG: Updating auto delete options for data: {settings_data}')
            cd = settings_data['auto_delete_cd']
            options = [
                SelectOption(label=label, value=seconds, description=f'Delete translation messages after {label}',
                             emoji=Emoji(name='⌛'), default=True if cd == seconds else False)
                for label, seconds in AUTO_DELETE_TIMERS
            ]
            options.insert(
                0, SelectOption(label='Never delete', value=-1, description='Never delete translation messages',
                                emoji=Emoji(name='⌛'), default=True if not cd else False)
            )
            return options

        def update_auto_translation_options(settings_data: dict | None) -> [SelectOption]:
            if settings_data and settings_data['auto_translate']:
                auto_translate_langs = settings_data['auto_translate']
            else:
                auto_translate_langs = []
            options = []
            for code in AUTO_TRANSLATE_OPTIONS:
                full_name = get_language_name(code, add_native=True)
                options.append(
                    SelectOption(label=full_name, value=code,
                                 description=f'Automatically translate messages to {full_name}',
                                 default=code in auto_translate_langs))
            return options

        guild_data = update_guild_data()
        category_list = [channel for channel in await guild.get_all_channels()
                         if channel.type == ChannelType.GUILD_CATEGORY]
        text_channel_list = [channel for channel in await guild.get_all_channels()
                             if channel.type == ChannelType.GUILD_TEXT]
        text_channel_hash = {int(channel.id): channel for channel in text_channel_list}

        # region Admin Panel
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
                'footer': FOOTER
            }
            embed = Embed(**embed_dict)

            labels = ['server', 'categories', 'channels']
            settings_buttons = [
                Button(style=ButtonStyle.SECONDARY, label=label.title(), custom_id=f'to_{label}_settings',
                       emoji=Emoji(id='1075539703014633512')) for label in labels]

            linked_channels_button = Button(style=ButtonStyle.SECONDARY, label='Linked Channels',
                                            custom_id='to_links_settings', emoji=Emoji(id='1075539703014633512'))

            shop_button = Button(style=ButtonStyle.LINK, label='Buy Tokens', url='https://www.google.com/',
                                 emoji=Emoji(id='1075540183941914788'))
            support_button = Button(style=ButtonStyle.SECONDARY,
                                    label='Support', custom_id='support', emoji=Emoji(id='1075539728553750621'))
            rows = [
                ActionRow(components=[*settings_buttons, linked_channels_button]),
                ActionRow(components=[shop_button, support_button])
            ]
            return embed, rows, [*settings_buttons, linked_channels_button, shop_button, support_button]

        # endregion
        # region Server Settings
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
                'footer': FOOTER
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

        # endregion
        # region Category Settings
        async def create_category_settings_embed() -> (Embed, [ActionRow], [Component]):
            embed_dict = {
                'title': f'`{guild.name}` - Category Settings',
                'description': f'This is the `Category Settings` page, you can make changes here that '
                               f'affect a categories and all the channels under it. '
                               f'\n\nChoose a category from the dropdown to view its configuration.',
                'color': EMBED_COLOUR,
                'footer': FOOTER
            }
            disable_reset_button, disable_edit_button = True, True
            if selected_category:
                cursor.execute('SELECT * FROM category WHERE id = ?', (selected_category,))
                selected_category_data = cursor.fetchone()
                disable_edit_button = False
                if selected_category_data:
                    selected_category_data = dict(selected_category_data)
                    auto_delete_string = get_auto_delete_timer_string(selected_category_data['auto_delete_cd'])
                    disable_reset_button = False
                else:
                    auto_delete_string = get_auto_delete_timer_string(None)

                langs_string = language_list_string(selected_category_data)
                affected_string = channel_list_string(text_channel_list, selected_category)

                embed_dict['fields'] = [
                    EmbedField(name=f'Auto Translation', value=langs_string, inline=True),
                    EmbedField(name='Auto Delete', value=auto_delete_string, inline=True),
                    EmbedField(name='Channels Affected', value=affected_string)
                ]
            embed = Embed(**embed_dict)
            back_button = Button(style=ButtonStyle.SECONDARY,
                                 label='Back', custom_id='to_homepage', emoji=Emoji(id='1075538962787082250'))
            edit_button = Button(style=ButtonStyle.PRIMARY, label='Edit', custom_id='edit_category_settings',
                                 emoji=Emoji(name='✏️'), disabled=disable_edit_button)
            reset_button = Button(style=ButtonStyle.PRIMARY, label='Reset', custom_id='reset_category_settings',
                                  emoji=Emoji(name='🔁'), disabled=disable_reset_button)
            category_select = SelectMenu(
                placeholder='Select a category...',
                custom_id='category_select',
                type=ComponentType.CHANNEL_SELECT,
                channel_types=[ChannelType.GUILD_CATEGORY]
            )
            rows = spread_to_rows(category_select, back_button, edit_button, reset_button)
            return embed, rows, [category_select, back_button, edit_button, reset_button]

        async def create_category_edit_embed() -> (Embed, [ActionRow], [Component]):
            category = next(channel for channel in category_list
                            if channel.id == selected_category)
            if not category:
                return create_category_settings_embed()

            embed_dict = {
                'title': f'`{category.name}` - Edit Category',
                'description': f'You are editing the `{category.name}` category, changes affect all associated text '
                               f'channels.'
                               '\n\nSettings on this page:\n'
                               '`Auto Translation` Dropdown for automatic translation languages.\n'
                               '`Auto Delete` Dropdown for translation message lifetime.',
                'color': EMBED_COLOUR,
                'footer': FOOTER
            }
            embed = Embed(**embed_dict)
            auto_translate_select = SelectMenu(
                placeholder='Select languages for auto translation...',
                custom_id='auto_translate_category',
                options=auto_translation_options,
                min_values=0,
                max_values=3
            )
            auto_delete_select = SelectMenu(
                custom_id='auto_delete_category',
                options=auto_delete_options,
            )
            back_button = Button(style=ButtonStyle.SECONDARY,
                                 label='Back', custom_id='to_category_settings', emoji=Emoji(id='1075538962787082250'))
            return (embed, spread_to_rows(auto_translate_select, auto_delete_select, back_button),
                    [auto_translate_select, auto_delete_select, back_button])

        # endregion
        # region Channel Settings
        async def create_channel_settings_embed() -> (Embed, [ActionRow], [Component]):
            embed_dict = {
                'title': f'`{guild.name}` - Channel Settings',
                'description': f'This is the `Channel Settings` page, you can make changes here that '
                               f'affect a single channel.'
                               f'\n\nChoose a channel from the dropdown to view its configuration.',
                'color': EMBED_COLOUR,
                'footer': FOOTER
            }
            disable_reset_button, disable_edit_button = True, True
            if selected_channel:
                cursor.execute('SELECT * FROM channel WHERE id = ?', (selected_channel,))
                selected_channel_data = cursor.fetchone()
                disable_edit_button = False
                if selected_channel_data:
                    selected_channel_data = dict(selected_channel_data)
                    auto_delete_string = get_auto_delete_timer_string(selected_channel_data['auto_delete_cd'])
                    disable_reset_button = False
                else:
                    auto_delete_string = get_auto_delete_timer_string(None)

                langs_string = language_list_string(selected_channel_data)

                embed_dict['fields'] = [
                    EmbedField(name=f'Auto Translation', value=langs_string, inline=True),
                    EmbedField(name='Auto Delete', value=auto_delete_string, inline=True)
                ]
            embed = Embed(**embed_dict)
            back_button = Button(style=ButtonStyle.SECONDARY,
                                 label='Back', custom_id='to_homepage', emoji=Emoji(id='1075538962787082250'))
            edit_button = Button(style=ButtonStyle.PRIMARY, label='Edit', custom_id='edit_channel_settings',
                                 emoji=Emoji(name='✏️'), disabled=disable_edit_button)
            reset_button = Button(style=ButtonStyle.PRIMARY, label='Reset', custom_id='reset_channel_settings',
                                  emoji=Emoji(name='🔁'), disabled=disable_reset_button)
            channel_select = SelectMenu(
                placeholder='Select a channel...',
                custom_id='channel_select',
                type=ComponentType.CHANNEL_SELECT,
                channel_types=[ChannelType.GUILD_TEXT]
            )
            rows = spread_to_rows(channel_select, back_button, edit_button, reset_button)
            return embed, rows, [channel_select, back_button, edit_button, reset_button]

        async def create_channel_edit_embed() -> (Embed, [ActionRow], [Component]):
            channel = next(channel for channel in text_channel_list
                           if channel.id == selected_channel)
            if not channel:
                return create_channel_settings_embed()

            embed_dict = {
                'title': f'`{channel.name}` - Edit Channel',
                'description': f'You are editing {channel.mention}, changes affect only this channel.'
                               '\n\nSettings on this page:\n'
                               '`Auto Translation` Dropdown for automatic translation languages.\n'
                               '`Auto Delete` Dropdown for translation message lifetime.',
                'color': EMBED_COLOUR,
                'footer': FOOTER
            }
            embed = Embed(**embed_dict)
            auto_translate_select = SelectMenu(
                placeholder='Select languages for auto translation...',
                custom_id='auto_translate_channel',
                options=auto_translation_options,
                min_values=0,
                max_values=3
            )
            auto_delete_select = SelectMenu(
                custom_id='auto_delete_channel',
                options=auto_delete_options,
            )
            back_button = Button(style=ButtonStyle.SECONDARY,
                                 label='Back', custom_id='to_channel_settings', emoji=Emoji(id='1075538962787082250'))
            return (embed, spread_to_rows(auto_translate_select, auto_delete_select, back_button),
                    [auto_translate_select, auto_delete_select, back_button])

        async def create_links_settings_embed() -> (Embed, [ActionRow], [Component]):

            embed_dict = {
                'title': f'`{guild.name}` - Linked Channel Settings',
                'description': f'You are viewing your server\'s linked channels, select a channel below and then use '
                               f'the second dropdown to select a link from that channel to others.',
                'color': EMBED_COLOUR,
                'footer': FOOTER
            }

            embed = Embed(**embed_dict)

            channel_select_links = SelectMenu(
                placeholder='Select a channel...',
                custom_id='links_channel_select',
                type=ComponentType.CHANNEL_SELECT,
                channel_types=[ChannelType.GUILD_TEXT]
            )
            link_select = None
            if links_selected_channel:
                links = group_channel_links(links_selected_channel, cursor)
                print(links)
                link_options = []
                for i, link in enumerate(links):
                    label = '→ ' + ', '.join(['#' + text_channel_hash[channel_to_id].name
                                              for channel_to_id in link["channels"]])
                    description = ', '.join([get_language_name(lang)
                                             for lang in link["languages"]])
                    link_options.append(
                        SelectOption(label=label, value=i, description=description, default=False))

                if link_options:
                    link_select = SelectMenu(
                        placeholder='Select a link configuration...',
                        custom_id='links_link_select',
                        options=link_options
                    )
            back_button = Button(style=ButtonStyle.SECONDARY, label='Back', custom_id='to_homepage',
                                 emoji=Emoji(id='1075538962787082250'))
            create_link_button = Button(style=ButtonStyle.SUCCESS, label='New Link', custom_id='to_new_link',
                                        emoji=Emoji(name='➕'), disabled=not links_selected_channel)
            delete_link_button = Button(style=ButtonStyle.DANGER, label='Delete Link', custom_id='delete_link',
                                        emoji=Emoji(name='✖️'), disabled=not selected_link)

            return (
                embed,
                spread_to_rows(channel_select_links, link_select, back_button, create_link_button, delete_link_button),
                [channel_select_links, link_select, back_button, create_link_button, delete_link_button])

        async def create_new_link_embed() -> (Embed, [ActionRow], [Component]):
            from_channel = text_channel_hash[int(links_selected_channel)]
            embed_dict = {
                'title': f'`#{from_channel.name}` - New Link',
                'description': f'You are creating a link from {from_channel.mention}, select target channels and '
                               f'languages using the dropdowns below.',
                'color': EMBED_COLOUR,
                'footer': FOOTER
            }

            embed = Embed(**embed_dict)

            new_link_channel_select = SelectMenu(
                placeholder='Link channel to...',
                custom_id='new_link_channel_select',
                type=ComponentType.CHANNEL_SELECT,
                channel_types=[ChannelType.GUILD_TEXT],
                max_values=5  # todo limit to max 5 links
            )

            new_link_languages_select = SelectMenu(
                placeholder='Select languages for auto translation...',
                custom_id='new_link_languages_select',
                options=auto_translation_options,
                max_values=3
            )

            save_disabled = not (new_link_selected_languages and new_link_selected_channels)

            back_button = Button(style=ButtonStyle.SECONDARY, label='Back', custom_id='to_links_settings',
                                 emoji=Emoji(id='1075538962787082250'))
            save_button = Button(style=ButtonStyle.SUCCESS, label='Save', custom_id='new_link_save',
                                 emoji=Emoji(name='✅'), disabled=save_disabled)

            return (embed, spread_to_rows(new_link_channel_select, new_link_languages_select, back_button, save_button),
                    [new_link_channel_select, new_link_languages_select, back_button, save_button])

        # endregion
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
                    case 'to_server_settings':
                        guild_data = update_guild_data()
                        auto_delete_options = update_auto_delete_options(guild_data)
                        next_embed_function = create_server_settings_embed
                    case 'to_categories_settings':
                        selected_category = None
                        next_embed_function = create_category_settings_embed
                    case 'to_channels_settings':
                        selected_channel = None
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
                        conn.commit()
                        guild_data = update_guild_data()
                        auto_delete_options = update_auto_delete_options(guild_data)
                        next_embed_function = create_server_settings_embed
                    # endregion
                    # region Category Settings
                    case 'category_select':
                        selected_category = button_ctx.data.values[0]
                        next_embed_function = create_category_settings_embed
                    case 'reset_category_settings':
                        if selected_category:
                            cursor.execute('DELETE FROM category WHERE id=?;', (int(selected_category),))
                            conn.commit()
                        next_embed_function = create_category_settings_embed
                    case 'to_category_settings':
                        selected_category = None
                        next_embed_function = create_category_settings_embed
                    case 'edit_category_settings':
                        category_data = await update_category_data()
                        auto_delete_options = update_auto_delete_options(category_data)
                        auto_translation_options = update_auto_translation_options(category_data)
                        next_embed_function = create_category_edit_embed
                    case 'auto_delete_category':
                        new_cooldown = int(button_ctx.data.values[0])
                        if new_cooldown == -1:
                            new_cooldown = None

                        cursor.execute(f"UPDATE category SET auto_delete_cd=? WHERE id=?;",
                                       (new_cooldown, int(selected_category)))
                        conn.commit()
                        category_data = await update_category_data()
                        auto_delete_options = update_auto_delete_options(category_data)
                        next_embed_function = create_category_edit_embed
                    case 'auto_translate_category':
                        values = button_ctx.data.values
                        values = None if not values else json.dumps(values)
                        print(f'DEBUG: updating category {selected_category} auto-translate with {values}')
                        cursor.execute(f"UPDATE category SET auto_translate=? WHERE id=?;",
                                       (values, int(selected_category)))
                        conn.commit()
                        category_data = await update_category_data()
                        auto_translation_options = update_auto_translation_options(category_data)
                        next_embed_function = create_category_edit_embed
                    # endregion
                    # region Channel Settings
                    case 'channel_select':
                        selected_channel = button_ctx.data.values[0]
                        next_embed_function = create_channel_settings_embed
                    case 'reset_channel_settings':
                        if selected_channel:
                            cursor.execute('DELETE FROM channel WHERE id=?;', (int(selected_channel),))
                            conn.commit()
                        next_embed_function = create_channel_settings_embed
                    case 'to_channel_settings':
                        selected_channel = None
                        next_embed_function = create_channel_settings_embed
                    case 'edit_channel_settings':
                        category_data = await update_channel_data()
                        auto_delete_options = update_auto_delete_options(category_data)
                        auto_translation_options = update_auto_translation_options(category_data)
                        next_embed_function = create_channel_edit_embed
                    case 'auto_delete_channel':
                        new_cooldown = int(button_ctx.data.values[0])
                        if new_cooldown == -1:
                            new_cooldown = None

                        cursor.execute(f"UPDATE channel SET auto_delete_cd=? WHERE id=?;",
                                       (new_cooldown, int(selected_channel)))
                        conn.commit()
                        channel_data = await update_channel_data()
                        auto_delete_options = update_auto_delete_options(channel_data)
                        next_embed_function = create_channel_edit_embed
                    case 'auto_translate_channel':
                        values = button_ctx.data.values
                        values = None if not values else json.dumps(values)
                        print(f'DEBUG: updating channel {selected_channel} auto-translate with {values}')
                        cursor.execute(f"UPDATE channel SET auto_translate=? WHERE id=?;",
                                       (values, int(selected_channel)))
                        conn.commit()
                        channel_data = await update_channel_data()
                        auto_translation_options = update_auto_translation_options(channel_data)
                        next_embed_function = create_channel_edit_embed

                    # endregion
                    # region Links Settings
                    case 'to_links_settings':
                        links_selected_channel = None
                        selected_link = None
                        new_link_selected_languages, new_link_selected_channels = None, None
                        next_embed_function = create_links_settings_embed
                    case 'links_channel_select':
                        links_selected_channel = button_ctx.data.values[0]
                        next_embed_function = create_links_settings_embed
                    case 'links_link_select':
                        selected_link = button_ctx.data.values[0]
                        next_embed_function = create_links_settings_embed
                    case 'link_delete':
                        next_embed_function = create_links_settings_embed

                    case 'to_new_link':
                        auto_translation_options = update_auto_translation_options(None)
                        next_embed_function = create_new_link_embed
                    case 'new_link_channel_select':
                        new_link_selected_channels = button_ctx.data.values
                        next_embed_function = create_new_link_embed
                    case 'new_link_languages_select':
                        new_link_selected_languages = button_ctx.data.values
                        auto_translation_options = update_auto_translation_options(
                            {'auto_translate': new_link_selected_languages})
                        next_embed_function = create_new_link_embed
                    case 'new_link_save':
                        print(f'DEBUG: creating new link from {links_selected_channel} to '
                              f'{new_link_selected_channels} in langs {new_link_selected_languages}')

                        data = [(links_selected_channel, channel_id, json.dumps(new_link_selected_languages))
                                for channel_id in new_link_selected_channels if channel_id != links_selected_channel]
                        for d in data:
                            print(d)
                        cursor.executemany('INSERT INTO channel_link VALUES (?, ?, ?)', data)
                        conn.commit()
                        new_link_selected_languages, new_link_selected_channels = None, None
                        next_embed_function = create_links_settings_embed
                    case 'delete_link':
                        # todo delete associated database entries
                        selected_link = None
                        next_embed_function = create_links_settings_embed
                    # endregion

                    # region Fallback
                    case _:
                        await message.edit(embeds=Embed(
                            description=f'**Uh oh! Something went wrong. '
                                        f'Please try using </{ctx.data.name}:{ctx.data.id}> again.**\n\n'
                                        f'*If issues persist, contact* <@275018879779078155>', footer=FOOTER))
                        break
                    # endregion
                next_embed, action_rows, all_components = await next_embed_function()
                message = await button_ctx.edit(embeds=next_embed, components=action_rows)

            except asyncio.TimeoutError:
                await message.edit(embeds=Embed(
                    description=f'**Your session has expired, please use </{ctx.data.name}:{ctx.data.id}> '
                                f'again if you would like to continue.**'))
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

    client.start()  # start discord client

    # close cursor and database connection
    cursor.close()
    conn.close()


if __name__ == '__main__':
    main()
