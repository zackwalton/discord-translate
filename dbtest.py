import json
import sqlite3


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
        auto_translate TEXT,
        auto_delete_cd INTEGER
    )
''')

cursor.execute('''
    CREATE TABLE channel (
        id INTEGER PRIMARY KEY,
        auto_translate TEXT,
        auto_delete_cd INTEGER
    )
''')
cursor.execute('''
    CREATE TABLE channel_link (
        channel_from_id INTEGER NOT NULL,
        channel_to_id INTEGER NOT NULL,
        languages TEXT NOT NULL
    )
''')
# endregion

server_data = [(871132162261397534,), (2,), (3,)]
cursor.executemany("INSERT INTO guild (id) VALUES (?)", server_data)

lang_str = json.dumps(["en", "fr"])
lang_str2 = json.dumps(["af", "jv"])
category_data = [(871132162261397535, lang_str), (2, lang_str), (3, lang_str)]
cursor.executemany("INSERT INTO category (id, auto_translate) VALUES (?, ?)", category_data)

channel_data = [(1025240272197656598, lang_str), (1030694981624672336, lang_str), (4, lang_str)]
cursor.executemany("INSERT INTO channel (id, auto_translate) VALUES (?, ?)", channel_data)
channel_link_data = [(1025240272197656598, 1030694981624672336, lang_str),
                     (1025240272197656598, 1080961573759242310, lang_str2),
                     (1025240272197656598, 1030695005729333258, lang_str2),
                     (0, 1071191584953086052, lang_str)]
cursor.executemany("INSERT INTO channel_link (channel_from_id, channel_to_id, languages) "
                   "VALUES (?, ?, ?)", channel_link_data)
# Commit the changes to the database
conn.commit()

print_table_data("guild")
print_table_data("category")
print_table_data("channel")
print_table_data("channel_link")

print('\n\n')
categories = (871132162261397535, 871132162261397536, 1071191623196737647)
query = f"SELECT * FROM category WHERE id IN ({('?,'*(len(categories)-1))}?)"
print(query)
cursor.execute(query, categories)
for row in cursor.fetchall():
    print(dict(row))

# Close the cursor and the connection
cursor.close()
conn.close()

# RESOURCES

# LIST OF LANGUAGES FROM CHANNEL LINK
# cursor.execute(f"SELECT * FROM channel_links")
# for row in cursor.fetchall():
#     print(json.loads(row[2]))
