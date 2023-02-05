import os
import os
import sqlite3

from dotenv import load_dotenv
from interactions import Client, ClientPresence, PresenceActivity, PresenceActivityType, Intents, Message, \
    MessageReaction, get, Embed, EmbedFooter, EmbedAuthor

from constants import FLAG_DATA_REGIONAL
from translate import translate_text, translation_tostring


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

    async def should_translate(reaction: MessageReaction, message: Message, emoji: str):
        if reaction.member.bot:  # reaction was made by a bot
            return False
        if client.me.id == message.id:  # reaction is on a translation message
            return False
        if emoji not in FLAG_DATA_REGIONAL:
            return False
        return True

    @client.event(name="on_message_reaction_add")
    async def reaction_add(reaction: MessageReaction):
        print(reaction)
        # get the message they reacted to
        message: Message = await get(
            client,
            Message,
            parent_id=int(reaction.channel_id),
            object_id=int(reaction.message_id)
        )

        emoji = reaction.emoji.name

        if not await should_translate(reaction, message, emoji):
            return

        translated_text = await translation_tostring(
            translate_text(
                FLAG_DATA_REGIONAL[emoji],  # target languages
                message.content  # text to translate
            )
        )

        embed_dict: dict = {
            "author": EmbedAuthor(name=reaction.member.name),
            "description": translated_text,
            "color": 0x56b0fd,
            "footer": EmbedFooter(text=f'From English ・ by {reaction.member.name}'),
        }
        embed = Embed(**embed_dict)
        await message.reply(embeds=[embed])

    client.start()


if __name__ == '__main__':
    main()
