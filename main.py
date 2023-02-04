import os
import sqlite3

import interactions
from dotenv import load_dotenv
from interactions import Client, ClientPresence, PresenceActivity, PresenceActivityType, Intents, Message, \
    MessageReaction, get, Button, ButtonStyle, spread_to_rows, Embed, EmbedFooter, EmbedAuthor
from translate import translate_text


def main():
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

    async def should_translate(reaction: MessageReaction, message: Message):
        if reaction.member.bot:  # reaction was made by a bot
            return False
        if client.me.id == message.id:  # reaction is on a translation message
            await message.reply('')
            return False
        return True

    @client.event(name="on_message_reaction_add")
    async def reaction_add(reaction: MessageReaction):

        message: Message = await get(
            client, interactions.Message,
            parent_id=int(reaction.channel_id),
            object_id=int(reaction.message_id)
        )

        if not await should_translate(reaction, message):
            return

        text_to_translate

        embed_dict: dict = {
            "author": EmbedAuthor(name=reaction.member.name),
            "description": f"`EN:` That was a crazy round. gg man\n\n"
                           f"`FR:` c'était un tour fou, mec, gg",
            "color": 0x56b0fd,
            "footer": EmbedFooter(text=f'From English ・ requested by {reaction.member.name}'),
        }
        embed = Embed(**embed_dict)
        # button = Button(style=ButtonStyle.SUCCESS, label="CONFIRM", custom_id="confirm_btn")
        await message.reply(embeds=[embed])

    client.start()


if __name__ == '__main__':
    main()
