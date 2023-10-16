import asyncio
import json
import os
import re
import sqlite3
from pprint import pformat

from dotenv import load_dotenv
from interactions import (
    Client, Intents, Message, Embed, EmbedFooter, OptionType, Permissions, Member, ChannelSelectMenu,
    Guild, Button, ButtonStyle, ComponentContext, EmbedField, ActionRow, spread_to_rows, ChannelType, Activity,
    ActivityType, GuildText, StringSelectMenu, StringSelectOption, PartialEmoji,
    SlashContext, slash_command, component_callback, listen, slash_option, EmbedAttachment,
    GuildCategory)
from interactions.api.events import MessageReactionAdd, Component, Startup, NewThreadCreate, ThreadDelete, MessageCreate

from const import FLAG_DATA_REGIONAL
from translate import translate_text, detect_text_language, create_thread_trans_embed, \
    create_trans_embed, get_guild_tokens
from utils import (
    EMBED_PRIMARY, FOOTER, AUTO_DELETE_TIMERS, get_auto_delete_timer_string, get_language_name,
    AUTO_TRANSLATE_OPTIONS, language_list_string, channel_list_string, group_channel_links, get_total_links)

# region Start Bot
load_dotenv('.env')
token = os.getenv('DISCORD_TOKEN')
conn = sqlite3.connect("database.db")
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

client = Client(
    token=token,
    intents=(Intents.DEFAULT | Intents.MESSAGE_CONTENT | Intents.GUILD_MESSAGE_REACTIONS),
    activity=Activity(type=ActivityType.WATCHING, name="for language barriers!")
)


@listen(Startup)
async def on_startup():
    print("Bot has been launched successfully.")


# endregion

async def should_process(message: Message, reaction: MessageReactionAdd = None):
    if reaction:
        emoji = reaction.emoji.name  # emoji they reacted with
        if reaction.author.bot:  # reaction was made by a bot
            return False
        if reaction.reaction_count > 1:  # reaction was already made
            return False
        if emoji not in FLAG_DATA_REGIONAL or emoji == '🌐':
            return False
    else:  # no reaction on message
        if message.author.id == client.user.id:  # message was sent by the bot
            return False

    return True


# region Flag Reactions

@listen(MessageReactionAdd)
async def on_message_reaction_add(reaction: MessageReactionAdd):
    print('got reaction')
    emoji = reaction.emoji.name  # emoji they reacted with
    message = reaction.message

    if not await should_process(message, reaction=reaction):
        return

    if message.message_reference:
        referenced_message: Message = await message.fetch_referenced_message()
        # update translated message to the original message if reaction on translation message
        if referenced_message and client.user.id == message.author.id:
            message = referenced_message
    embed_dict: dict = {
        "color": EMBED_PRIMARY
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
        embed_dict['footer'] = EmbedFooter(
            text=f'{reaction.author.global_name}・ {confidence_percent} Confident')
        embed = Embed(**embed_dict)

    else:  # text translation
        translation_data = await translate_text(
            FLAG_DATA_REGIONAL[emoji],  # target languages
            message.content  # text to translate
        )
        if not translation_data:
            return
        target_langs = FLAG_DATA_REGIONAL[emoji]
        embed = await create_trans_embed(translation_data, reaction.author, target_langs)
    await message.reply(embed=embed)


# endregion

# region Message Event Handler
@listen(MessageCreate)
async def on_message_create(e: MessageCreate):
    message = e.message
    if not await should_process(message):
        return

    guild_data = cursor.execute("SELECT * FROM guild WHERE id = ?", (e.message.guild.id,))
    guild_data = dict(guild_data.fetchone())
    if not guild_data:
        return  # todo add guild to database and continue

    # thread message
    if message.channel.type in (ChannelType.GUILD_PRIVATE_THREAD, ChannelType.GUILD_PUBLIC_THREAD):
        await handle_thread_translation(message)
        return

    # handle category, thread, and server auto translation languages

    channel_id = message.channel.id
    links = [dict(link) for link in
             cursor.execute(
                 'SELECT * FROM channel_link WHERE channel_from_id = ?',
                 (channel_id,))
             .fetchall()]
    for link in links:
        channel_to_id = link['channel_to_id']
        channel_to: GuildText = await client.fetch_channel(channel_to_id)
        if channel_to.type == ChannelType.GUILD_TEXT:
            await channel_to.send(message.content)
    await message.reply('test')


async def handle_thread_translation(message: Message):
    cursor.execute('SELECT * FROM thread WHERE thread_id = ?', (message.channel.id,))
    thread_data = cursor.fetchone()
    if thread_data:
        thread_data = dict(thread_data)
        languages = thread_data['languages']
        if languages:
            languages = json.loads(languages)
            translation_data = await translate_text(languages, message.content)
            if not translation_data:
                return
            embed = await create_thread_trans_embed(translation_data, message.author)
            await message.reply(embed=embed, silent=True)  # noqa
    return


# endregion

# region Thread Event Handler

async def create_thread_select_menu(selected: [] = None):
    selected = selected if selected else []
    return StringSelectMenu(
        *[
            StringSelectOption(label='English', value='en', emoji=PartialEmoji(name='🇬🇧'),
                               default='en' in selected),
            StringSelectOption(label='German', value='de', emoji=PartialEmoji(name='🇩🇪'), default='de' in selected),
            StringSelectOption(label='French', value='fr', emoji=PartialEmoji(name='🇫🇷'), default='fr' in selected),
            StringSelectOption(label='Spanish', value='es', emoji=PartialEmoji(name='🇪🇸'),
                               default='es' in selected),
        ],
        custom_id='thread_auto_translation',
        placeholder='Select languages for auto-translation...',
        min_values=0,
        max_values=2
    )


thread_translation_message = 'Choose auto-translation languages for messages in this thread!'


@listen(NewThreadCreate)
async def on_new_thread_create(e: NewThreadCreate):
    thread = e.thread
    print('DEBUG: Thread created!')
    select_menu = await create_thread_select_menu()
    await asyncio.sleep(0.1)
    await thread.send(thread_translation_message, components=spread_to_rows(select_menu), silent=True)


@listen(ThreadDelete)
async def on_thread_delete(e: ThreadDelete):
    cursor.execute('DELETE FROM thread WHERE thread_id = ?', (e.thread.id,))
    conn.commit()


@component_callback('thread_auto_translation')
async def thread_auto_translation(ctx: ComponentContext):
    select_menu = await create_thread_select_menu(ctx.values)
    await ctx.edit_origin(content=thread_translation_message, components=select_menu)

    # delete or update thread data in database
    if ctx.values:
        cursor.execute(
            'REPLACE INTO thread (thread_id, languages) VALUES (?, ?)',
            (ctx.channel_id, json.dumps(ctx.values)))
    else:
        cursor.execute('DELETE FROM thread WHERE thread_id = ?', (ctx.channel_id,))
    conn.commit()


# endregion

# region Commands
@slash_command(name='t', description="base command")
async def translate_command(_: SlashContext):
    pass


@translate_command.subcommand(sub_cmd_name="text", sub_cmd_description="Translate text")
@slash_option(
    name="text",
    description='Text to translate',
    required=True,
    opt_type=OptionType.STRING)
@slash_option(
    name="languages",
    description='Target languages',
    required=True,
    opt_type=OptionType.STRING)
async def text_command(ctx: SlashContext, text: str = None, languages: str = None):
    await ctx.send(f"You selected the command_name sub command and put in {text} and "
                   f"{re.findall('[a-z]{2}', languages)}")


MAX_LINKS = 8


@slash_command(name='admin', default_member_permissions=Permissions.ADMINISTRATOR)
async def admin(ctx: SlashContext):
    """ Configurate your server's translation settings """
    guild: Guild = await client.fetch_guild(ctx.guild_id)

    def update_guild_data() -> dict:
        """ Returns updated guild data from the database """
        cursor.execute("SELECT * FROM guild WHERE id = ?", [int(guild.id)])
        return dict(cursor.fetchone())

    async def update_category_data() -> [dict]:
        """ Returns updated category data from the database """
        print(f'DEBUG: Updating category data for {selected_category.name}')
        cursor.execute(f"SELECT * FROM category WHERE id = (?)", (selected_category.id,))
        query = cursor.fetchone()
        if query:
            return dict(query)
        else:
            print('DEBUG: Did not find the category, creating entry.')
            cursor.execute(f"INSERT INTO category (id) VALUES (?)", (selected_category.id,))
            return await update_category_data()

    async def update_channel_data() -> [dict]:
        """ Returns updated channel data from the database """
        print(f'DEBUG: Updating channel data for {selected_channel.id}')
        cursor.execute(f"SELECT * FROM channel WHERE id = (?)", (selected_channel.id,))
        query = cursor.fetchone()
        if query:
            return dict(query)
        else:
            print('DEBUG: Did not find the channel, creating entry.')
            cursor.execute(f"INSERT INTO channel (id) VALUES (?)", (selected_channel.id,))
            return await update_channel_data()

    def update_auto_delete_options(settings_data: dict) -> [StringSelectOption]:
        print(f'DEBUG: Updating auto delete options for data: {settings_data}')
        cd = settings_data['auto_delete_cd']
        options = [
            StringSelectOption(label=label, value=seconds, description=f'Delete translation messages after {label}',
                               emoji=PartialEmoji(name='⌛'), default=True if cd == seconds else False)
            for label, seconds in AUTO_DELETE_TIMERS
        ]
        options.insert(
            0, StringSelectOption(label='Never delete', value="-1", description='Never delete translation messages',
                                  emoji=PartialEmoji(name='⌛'), default=True if not cd else False)
        )
        return options

    def update_auto_translation_options(settings_data: dict | None) -> [StringSelectOption]:
        if settings_data and settings_data['auto_translate']:
            auto_translate_langs = settings_data['auto_translate']
        else:
            auto_translate_langs = []
        options = []
        for code in AUTO_TRANSLATE_OPTIONS:
            full_name = get_language_name(code, add_native=True)
            options.append(
                StringSelectOption(label=full_name, value=code,
                                   description=f'Automatically translate messages to {full_name}',
                                   default=code in auto_translate_langs))
        return options

    guild_data = update_guild_data()
    category_list = [channel for channel in guild.channels
                     if channel.type == ChannelType.GUILD_CATEGORY]
    text_channel_list = [channel for channel in guild.channels
                         if channel.type == ChannelType.GUILD_TEXT]
    text_channel_hash = {int(channel.id): channel for channel in text_channel_list}
    text_channel_ids = list(text_channel_hash.keys())

    # region Admin Panel
    async def create_home_embed() -> (Embed, [ActionRow], [Component]):
        embed_dict = {
            'title': f'`{guild.name}`',
            'thumbnail': EmbedAttachment(url=guild.icon.url),
            'description': 'This is the `Admin Panel`, use the buttons below to configure your server.',
            'fields': [
                EmbedField(name=f'Tokens',
                           value=str(guild_data['tokens_remaining']), inline=True),
                EmbedField(name='Characters Translated', value=str(guild_data['characters_translated']),
                           inline=True)
            ],
            'color': EMBED_PRIMARY,
            'footer': FOOTER
        }
        embed = Embed(**embed_dict)

        labels = ['server', 'categories', 'channels']
        settings_buttons = [
            Button(style=ButtonStyle.SECONDARY, label=label.title(), custom_id=f'to_{label}_settings',
                   emoji=PartialEmoji(id='1075539703014633512')) for label in labels]

        linked_channels_button = Button(style=ButtonStyle.SECONDARY, label='Linked Channels',
                                        custom_id='to_links_settings', emoji=PartialEmoji(id='1075539703014633512'))

        shop_button = Button(style=ButtonStyle.SECONDARY, label='Buy Tokens',
                             emoji=PartialEmoji(id='1075540183941914788'))
        support_button = Button(style=ButtonStyle.SECONDARY,
                                label='Support', custom_id='support', emoji=PartialEmoji(id='1075539728553750621'))
        return (embed, spread_to_rows(*settings_buttons, linked_channels_button, shop_button, max_in_row=4),
                [*settings_buttons, linked_channels_button, shop_button, support_button])

    # endregion
    # region Server Settings
    async def create_server_settings_embed() -> (Embed, [ActionRow], [Component]):
        flag_t = guild_data['flag_translation']
        cmd_t = guild_data['command_translation']

        embed_dict = {
            'title': f'`{guild.name}` - Server Settings',
            'thumbnail': EmbedAttachment(url=guild.icon.url),
            'description': 'This is the `Server Settings` page, changes here affect the *whole* server. '
                           '\n\nSettings on this page:\n'
                           '`Auto Delete` Dropdown for translation message lifetime.\n'
                           '`Flag/Command Translation` Buttons to toggle flag/command translations',
            'fields': [
                EmbedField(name=f'Flag Translation', value='Active' if flag_t else 'Not active', inline=True),
                EmbedField(name='Command Translation', value='Active' if cmd_t else 'Not active', inline=True)
            ],
            'color': EMBED_PRIMARY,
            'footer': FOOTER
        }
        embed = Embed(**embed_dict)
        print(F'AUTO DELETE OPTIONS: {auto_delete_options}')
        auto_delete_select = StringSelectMenu(
            *auto_delete_options,
            custom_id='auto_delete_guild'
        )
        back_button = Button(style=ButtonStyle.SECONDARY,
                             label='Back', custom_id='to_homepage', emoji=PartialEmoji(id='1075538962787082250'))
        flag_button = Button(style=ButtonStyle.SUCCESS if flag_t else ButtonStyle.DANGER, label='Flag Translation',
                             custom_id='flag_toggle', emoji=PartialEmoji(name='🇨🇦'))
        cmd_button = Button(style=ButtonStyle.SUCCESS if cmd_t else ButtonStyle.DANGER, label='Command Translation',
                            custom_id='command_toggle', emoji=PartialEmoji(id='1075542290698866759'))
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
            'color': EMBED_PRIMARY,
            'footer': FOOTER
        }
        disable_reset_button, disable_edit_button = True, True
        if selected_category:
            cursor.execute('SELECT * FROM category WHERE id = ?', (selected_category.id,))
            category_data = cursor.fetchone()
            disable_edit_button = False
            if category_data:
                category_data = dict(category_data)
                auto_delete_string = await get_auto_delete_timer_string(category_data['auto_delete_cd'])
                disable_reset_button = False
            else:
                auto_delete_string = await get_auto_delete_timer_string(None)

            langs_string = await language_list_string(category_data)
            affected_string = await channel_list_string(text_channel_list, selected_category)

            embed_dict['fields'] = [
                EmbedField(name=f'Auto Translation', value=langs_string, inline=True),
                EmbedField(name='Auto Delete', value=auto_delete_string, inline=True),
                EmbedField(name='Channels Affected', value=affected_string)
            ]
        embed = Embed(**embed_dict)
        back_button = Button(style=ButtonStyle.SECONDARY,
                             label='Back', custom_id='to_homepage', emoji=PartialEmoji(id='1075538962787082250'))
        edit_button = Button(style=ButtonStyle.PRIMARY, label='Edit', custom_id='edit_category_settings',
                             emoji=PartialEmoji(name='✏️'), disabled=disable_edit_button)
        reset_button = Button(style=ButtonStyle.PRIMARY, label='Reset', custom_id='reset_category_settings',
                              emoji=PartialEmoji(name='🔁'), disabled=disable_reset_button)
        category_select = ChannelSelectMenu(
            placeholder='Select a category...',
            custom_id='category_select',
            channel_types=[ChannelType.GUILD_CATEGORY]
        )
        rows = spread_to_rows(category_select, back_button, edit_button, reset_button)
        return embed, rows, [category_select, back_button, edit_button, reset_button]

    async def create_category_edit_embed() -> (Embed, [ActionRow], [Component]):
        category = next(channel for channel in category_list
                        if channel.id == selected_category.id)
        if not category:
            return create_category_settings_embed()

        embed_dict = {
            'title': f'`{category.name}` - Edit Category',
            'description': f'You are editing the `{category.name}` category, changes affect all associated text '
                           f'channels.'
                           '\n\nSettings on this page:\n'
                           '`Auto Translation` Dropdown for automatic translation languages.\n'
                           '`Auto Delete` Dropdown for translation message lifetime.',
            'color': EMBED_PRIMARY,
            'footer': FOOTER
        }
        embed = Embed(**embed_dict)
        auto_translate_select = StringSelectMenu(
            *auto_translation_options,
            placeholder='Select languages for auto translation...',
            custom_id='auto_translate_category',
            min_values=0,
            max_values=3
        )
        auto_delete_select = StringSelectMenu(
            *auto_delete_options,
            custom_id='auto_delete_category',
        )
        back_button = Button(style=ButtonStyle.SECONDARY,
                             label='Back', custom_id='to_category_settings',
                             emoji=PartialEmoji(id='1075538962787082250'))
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
            'color': EMBED_PRIMARY,
            'footer': FOOTER
        }
        disable_reset_button, disable_edit_button = True, True
        if selected_channel:
            cursor.execute('SELECT * FROM channel WHERE id = ?', (selected_channel.id,))
            channel_data = cursor.fetchone()
            disable_edit_button = False
            if channel_data:
                channel_data = dict(channel_data)
                auto_delete_string = await get_auto_delete_timer_string(int(channel_data['auto_delete_cd']))
                disable_reset_button = False
            else:
                auto_delete_string = await get_auto_delete_timer_string(None)

            langs_string = await language_list_string(channel_data)

            embed_dict['fields'] = [
                EmbedField(name=f'Auto Translation', value=langs_string, inline=True),
                EmbedField(name='Auto Delete', value=auto_delete_string, inline=True)
            ]
        embed = Embed(**embed_dict)
        back_button = Button(style=ButtonStyle.SECONDARY,
                             label='Back', custom_id='to_homepage', emoji=PartialEmoji(id='1075538962787082250'))
        edit_button = Button(style=ButtonStyle.PRIMARY, label='Edit', custom_id='edit_channel_settings',
                             emoji=PartialEmoji(name='✏️'), disabled=disable_edit_button)
        reset_button = Button(style=ButtonStyle.PRIMARY, label='Reset', custom_id='reset_channel_settings',
                              emoji=PartialEmoji(name='🔁'), disabled=disable_reset_button)
        channel_select = ChannelSelectMenu(
            placeholder='Select a channel...',
            custom_id='channel_select',
            channel_types=[ChannelType.GUILD_TEXT]
        )
        rows = spread_to_rows(channel_select, back_button, edit_button, reset_button)
        return embed, rows, [channel_select, back_button, edit_button, reset_button]

    async def create_channel_edit_embed() -> (Embed, [ActionRow], [Component]):
        channel = next(channel for channel in text_channel_list
                       if channel.id == selected_channel.id)
        if not channel:
            return create_channel_settings_embed()

        embed_dict = {
            'title': f'`{channel.name}` - Edit Channel',
            'description': f'You are editing {channel.mention}, changes affect only this channel.'
                           '\n\nSettings on this page:\n'
                           '`Auto Translation` Dropdown for automatic translation languages.\n'
                           '`Auto Delete` Dropdown for translation message lifetime.',
            'color': EMBED_PRIMARY,
            'footer': FOOTER
        }
        embed = Embed(**embed_dict)
        auto_translate_select = StringSelectMenu(
            *auto_translation_options,
            placeholder='Select languages for auto translation...',
            custom_id='auto_translate_channel',
            min_values=0,
            max_values=3
        )
        auto_delete_select = StringSelectMenu(
            *auto_delete_options,
            custom_id='auto_delete_channel',
        )
        back_button = Button(style=ButtonStyle.SECONDARY,
                             label='Back', custom_id='to_channel_settings',
                             emoji=PartialEmoji(id='1075538962787082250'))
        return (embed, spread_to_rows(auto_translate_select, auto_delete_select, back_button),
                [auto_translate_select, auto_delete_select, back_button])

    async def create_links_settings_embed() -> (Embed, [ActionRow], [Component]):

        embed = Embed(
            title=f'`{guild.name}` - Linked Channel Settings',
            description=f'You are viewing your server\'s linked channels, select a channel below and then use '
                        f'the second dropdown to select a link from that channel to others.',
            fields=[
                EmbedField(name=f'Total links', value=f'{server_links}/{MAX_LINKS}', inline=True),
            ],
            color=EMBED_PRIMARY,
            footer=FOOTER
        )

        channel_select_links = ChannelSelectMenu(
            placeholder='Select a channel...',
            custom_id='links_channel_select',
            channel_types=[ChannelType.GUILD_TEXT]
        )
        link_select = None
        if links_selected_channel:
            cursor.execute('SELECT * FROM channel_link WHERE channel_from_id = ?', (links_selected_channel.id,))
            response = cursor.fetchall()
            links = await group_channel_links(links_selected_channel, response)
            link_options = []
            for i, link in enumerate(links):
                label = '→ ' + ', '.join(['#' + text_channel_hash[channel_to_id].name
                                          for channel_to_id in link["channels"]])
                description = ', '.join([get_language_name(lang)
                                         for lang in link["languages"]])
                # create a value id in the form of 'from_id-to_id,to_id,to_id'
                value = (f'{links_selected_channel.id}-'
                         f'{",".join([str(channel_to_id) for channel_to_id in link["channels"]])}')
                link_options.append(
                    StringSelectOption(label=label, value=value, description=description,
                                       default=selected_link == value))

            if link_options:
                link_select = StringSelectMenu(
                    *link_options,
                    placeholder='Select a link configuration...',
                    custom_id='links_link_select',
                )
        back_button = Button(style=ButtonStyle.SECONDARY, label='Back', custom_id='to_homepage',
                             emoji=PartialEmoji(id='1075538962787082250'))
        new_link_button = Button(style=ButtonStyle.SUCCESS, label='New Link',
                                 custom_id='to_new_link', emoji=PartialEmoji(name='➕'),
                                 disabled=not links_selected_channel or server_links >= MAX_LINKS)
        delete_link_button = Button(style=ButtonStyle.DANGER, label='Delete Link', custom_id='delete_link',
                                    emoji=PartialEmoji(name='✖️'), disabled=selected_link is None)

        rows = spread_to_rows(back_button, new_link_button, delete_link_button)
        components = [channel_select_links, back_button, new_link_button, delete_link_button]
        if link_select:
            rows.insert(0, ActionRow(link_select))
            components.append(link_select)
        rows.insert(0, ActionRow(channel_select_links))

        return embed, rows, components

    async def create_new_link_embed() -> (Embed, [ActionRow], [Component]):
        from_channel = text_channel_hash[int(links_selected_channel.id)]
        embed = Embed(
            title=f'`#{from_channel.name}` - New Link',
            description=f'You are creating a link from {from_channel.mention}, select target channels and '
                        f'languages using the dropdowns below. *You cannot link a channel to itself.*',
            fields=[
                EmbedField(name=f'Total links', value=f'{server_links}/{MAX_LINKS}', inline=True),
            ],
            color=EMBED_PRIMARY,
            footer=FOOTER
        )

        new_link_channel_select = ChannelSelectMenu(
            placeholder='Link channel to...',
            custom_id='new_link_channel_select',
            channel_types=[ChannelType.GUILD_TEXT],
            max_values=(MAX_LINKS - server_links)
        )

        new_link_languages_select = StringSelectMenu(
            *auto_translation_options,
            placeholder='Select languages for auto translation...',
            custom_id='new_link_languages_select',
            max_values=2
        )

        save_disabled = not (new_link_selected_languages and new_link_selected_channels)

        back_button = Button(style=ButtonStyle.SECONDARY, label='Back', custom_id='to_links_settings',
                             emoji=PartialEmoji(id='1075538962787082250'))
        save_button = Button(style=ButtonStyle.SUCCESS, label='Save', custom_id='new_link_save',
                             emoji=PartialEmoji(name='✅'), disabled=save_disabled)

        return (embed, spread_to_rows(new_link_channel_select, new_link_languages_select, back_button, save_button),
                [new_link_channel_select, new_link_languages_select, back_button, save_button])

    # endregion
    next_embed, action_rows, all_components = await create_home_embed()
    message = await ctx.send(embeds=next_embed, components=action_rows)

    async def check(component: Component):
        if component.ctx.member.id != ctx.member.id:
            return False
        return True

    while True:
        try:
            component: Component = await client.wait_for_component(
                message, all_components, check=check, timeout=120)
            custom_id = component.ctx.custom_id
            await component.ctx.defer(edit_origin=True)
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
                    new_cooldown = int(component.ctx.values[0])
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
                    selected_category: GuildCategory | None = component.ctx.values[0]
                    next_embed_function = create_category_settings_embed
                case 'reset_category_settings':
                    if selected_category:
                        cursor.execute('DELETE FROM category WHERE id=?;', (selected_category.id,))
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
                    new_cooldown = int(component.ctx.values[0])
                    if new_cooldown == -1:
                        new_cooldown = None

                    cursor.execute(f"UPDATE category SET auto_delete_cd=? WHERE id=?;",
                                   (new_cooldown, selected_category.id))
                    conn.commit()
                    category_data = await update_category_data()
                    auto_delete_options = update_auto_delete_options(category_data)
                    next_embed_function = create_category_edit_embed
                case 'auto_translate_category':
                    values = component.ctx.values
                    values = None if not values else json.dumps(values)
                    print(f'DEBUG: updating category {selected_category.name} auto-translate with {values}')
                    cursor.execute(f"UPDATE category SET auto_translate=? WHERE id=?;",
                                   (values, selected_category.id))
                    conn.commit()
                    category_data = await update_category_data()
                    auto_translation_options = update_auto_translation_options(category_data)
                    next_embed_function = create_category_edit_embed
                # endregion
                # region Channel Settings
                case 'channel_select':
                    selected_channel: GuildText | None = component.ctx.values[0]  # noqa
                    next_embed_function = create_channel_settings_embed
                case 'reset_channel_settings':
                    if selected_channel:
                        cursor.execute('DELETE FROM channel WHERE id=?;', (selected_channel.id,))
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
                    new_cooldown = int(component.ctx.values[0])
                    if new_cooldown == -1:
                        new_cooldown = None

                    cursor.execute(f"UPDATE channel SET auto_delete_cd=? WHERE id=?;",
                                   (new_cooldown, selected_channel.id))
                    conn.commit()
                    channel_data = await update_channel_data()
                    auto_delete_options = update_auto_delete_options(channel_data)
                    next_embed_function = create_channel_edit_embed
                case 'auto_translate_channel':
                    values = component.ctx.values
                    values = None if not values else json.dumps(values)
                    print(f'DEBUG: updating channel {selected_channel.name} auto-translate with {values}')
                    cursor.execute(f"UPDATE channel SET auto_translate=? WHERE id=?;",
                                   (values, selected_channel.id))
                    conn.commit()
                    channel_data = await update_channel_data()
                    auto_translation_options = update_auto_translation_options(channel_data)
                    next_embed_function = create_channel_edit_embed

                # endregion
                # region Links Settings
                case 'to_links_settings':
                    links_selected_channel = None
                    selected_link = None
                    server_links = await get_total_links(cursor, text_channel_ids)
                    new_link_selected_languages, new_link_selected_channels = None, None
                    next_embed_function = create_links_settings_embed
                case 'links_channel_select':
                    links_selected_channel: GuildText | None = component.ctx.values[0]  # noqa
                    next_embed_function = create_links_settings_embed
                case 'links_link_select':
                    selected_link: str | None = component.ctx.values[0]
                    next_embed_function = create_links_settings_embed
                case 'link_delete':
                    next_embed_function = create_links_settings_embed

                case 'to_new_link':
                    auto_translation_options = update_auto_translation_options(None)
                    next_embed_function = create_new_link_embed
                case 'new_link_channel_select':
                    new_link_selected_channels = component.ctx.values
                    next_embed_function = create_new_link_embed
                case 'new_link_languages_select':
                    new_link_selected_languages = component.ctx.values
                    auto_translation_options = update_auto_translation_options(
                        {'auto_translate': new_link_selected_languages})
                    next_embed_function = create_new_link_embed
                case 'new_link_save':
                    print(f'DEBUG: creating new link from {links_selected_channel.name} to '
                          f'{", ".join([channel.name for channel in new_link_selected_channels])} '
                          f'with langs {new_link_selected_languages}')

                    data = [(links_selected_channel.id, channel.id, json.dumps(new_link_selected_languages))
                            for channel in new_link_selected_channels if channel.id != links_selected_channel.id]
                    for d in data:
                        print(d)
                    cursor.executemany('INSERT INTO channel_link VALUES (?, ?, ?)', data)
                    conn.commit()
                    server_links = await get_total_links(cursor, text_channel_ids)

                    new_link_selected_languages, new_link_selected_channels = None, None
                    next_embed_function = create_links_settings_embed
                case 'delete_link':
                    # in the form of 'from_id-to_id,to_id,to_id'
                    split = selected_link.split('-')
                    from_channel: str = split[0]
                    to_channels: [str] = split[1].split(',')

                    # delete associated link database entries
                    cursor.execute(
                        'DELETE FROM channel_link WHERE channel_from_id=? AND '
                        f"channel_to_id IN ({'?,' * (len(to_channels) - 1)}?)",
                        (from_channel, *to_channels))
                    conn.commit()
                    server_links -= len(to_channels)

                    selected_link = None
                    next_embed_function = create_links_settings_embed
                # endregion

                # region Fallback
                case _:
                    await ctx.edit(message, embeds=Embed(
                        description=f'**Uh oh! Something went wrong.'
                                    f'Please try using `/{ctx.command.name}` again.**\n\n'
                                    f'*If issues persist, contact an admin*', footer=FOOTER))
                    break
                # endregion
            next_embed, action_rows, all_components = await next_embed_function()
            message = await ctx.edit(message, embeds=next_embed, components=action_rows)

        except asyncio.TimeoutError:
            await message.edit(embed=Embed(
                description=f'**Your session has expired, please use `/{ctx.command.name}` again if you would '
                            f'like to continue.**'), components=[])
            break


@slash_command(
    name='ban',
    default_member_permissions=Permissions.ADMINISTRATOR,
)
@slash_option(
    name="member",
    description='User to ban from using translate features',
    required=True,
    opt_type=OptionType.USER
)
async def ban_command(ctx: SlashContext, member: Member):
    """ Ban a user from using the bot """

    #  https://interactionspy.readthedocs.io/en/latest/api.models.guild.html#interactions.api.models.guild.Guild.create_role
    ban_role_name = 'no-translate'
    guild = await client.fetch_guild(ctx.guild.id)
    roles = guild.roles
    print(pformat(roles))
    embed_dict: dict = {
        "color": EMBED_PRIMARY,
        "description": ""
    }

    role_names = [role.name for role in roles]
    # if the role does not exist yet, create it
    if ban_role_name not in role_names:
        await guild.create_role(
            ban_role_name,
            None,
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
        component: Component = await client.wait_for_component(message, button, timeout=30)
        await component.ctx.defer(edit_origin=True)
        custom_id = component.ctx.custom_id
        if custom_id == 'reset_perms_ban':
            reason = f'Removed potentially unsafe permissions attached to the `{ban_role_name}` role.'
            await guild.modify_role(ban_role.id, permissions=0, reason=reason)
            success_button = Button(style=ButtonStyle.SUCCESS, emoji=PartialEmoji(name='✅'),
                                    label='Success', custom_id='success', disabled=True)
            await component.ctx.edit(components=success_button)
    except asyncio.exceptions.TimeoutError:
        pass


# endregion

client.start(os.getenv('DISCORD_TOKEN'))  # start discord client

# close cursor and database connection
cursor.close()
conn.close()
