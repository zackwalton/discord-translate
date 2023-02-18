import json
import sqlite3

from interactions import SelectOption


def print_table_data(name: str):
    cursor.execute(f"SELECT * FROM {name}")
    print(f'\n{name} table:')
    for row in cursor.fetchall():
        print(dict(row))


# region Setup
# Connect to the database (or create a new database if it doesn't exist)
conn = sqlite3.connect('database.db')
conn.row_factory = sqlite3.Row
# Create a cursor to execute SQL statements
cursor = conn.cursor()

cursor.execute('PRAGMA foreign_keys = ON;')
cursor.execute('DROP TABLE IF EXISTS guild')
cursor.execute('DROP TABLE IF EXISTS category')
cursor.execute('DROP TABLE IF EXISTS channel')
cursor.execute('DROP TABLE IF EXISTS channel_link')

# Execute some SQL statements
cursor.execute('''
    CREATE TABLE guild (
        id INTEGER PRIMARY KEY,
        tokens INTEGER NOT NULL DEFAULT 10000,
        flag_translation BOOL NOT NULL DEFAULT 1,
        command_translation BOOL NOT NULL DEFAULT 1,
        characters_translated INTEGER NOT NULL DEFAULT 0,
        auto_delete_cd INTEGER
    )
''')

cursor.execute('''
    CREATE TABLE category (
        id INTEGER PRIMARY KEY,
        guild_id INTEGER NOT NULL,
        auto_delete_cd INTEGER,
        FOREIGN KEY (guild_id) REFERENCES guild(id) ON DELETE CASCADE
    )
''')

cursor.execute('''
    CREATE TABLE channel (
        id INTEGER PRIMARY KEY,
        category_id INTEGER NOT NULL,
        auto_delete_cd INTEGER,
        FOREIGN KEY (category_id) REFERENCES category(id) ON DELETE CASCADE
    )
''')
cursor.execute('''
    CREATE TABLE channel_link (
        channel_from_id INTEGER REFERENCES channel(id) ON DELETE CASCADE,
        channel_to_id INTEGER REFERENCES channel(id) ON DELETE CASCADE,
        language TEXT NOT NULL,
        PRIMARY KEY (channel_from_id, channel_to_id)
    )
''')
# endregion

server_data = [(871132162261397534,), (2,), (3,)]
cursor.executemany("INSERT INTO guild (id) VALUES (?)", server_data)

category_data = [(1, 871132162261397534), (2, 2), (3, 3)]
cursor.executemany("INSERT INTO category (id, guild_id) VALUES (?, ?)", category_data)

channel_data = [(6, 1), (5, 2), (4, 3)]
cursor.executemany("INSERT INTO channel (id, category_id) VALUES (?, ?)", channel_data)

lang_str = json.dumps(["en", "fr"])
channel_link_data = [(4, 5, lang_str), (6, 5, lang_str), (4, 6, lang_str), (4, 4, lang_str)]
cursor.executemany("INSERT INTO channel_link (channel_from_id, channel_to_id, language) "
                   "VALUES (?, ?, ?)", channel_link_data)
# Commit the changes to the database
conn.commit()

print_table_data("guild")
print_table_data("category")
print_table_data("channel")
print_table_data("channel_link")

# Close the cursor and the connection
cursor.close()
conn.close()

# RESOURCES

# LIST OF LANGUAGES FROM CHANNEL LINK
# cursor.execute(f"SELECT * FROM channel_links")
# for row in cursor.fetchall():
#     print(json.loads(row[2]))
