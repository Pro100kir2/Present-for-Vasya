import os
import mysql.connector
import argparse
from dotenv import load_dotenv

load_dotenv()

# Настройки базы данных через переменные окружения
MYSQL_USER = os.getenv('MYSQL_USER')
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD')
MYSQL_HOST = os.getenv('MYSQL_HOST')
MYSQL_DB = os.getenv('MYSQL_DB')


# Подключение к БД
def get_db_connection():
    connection = mysql.connector.connect(
        host=MYSQL_HOST,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DB
    )
    return connection


# Вывести всех пользователей
def list_users():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM users;")  # <-- Замени 'users' на свою таблицу если нужно
    users = cursor.fetchall()
    if users:
        print("Список пользователей:")
        for user in users:
            print(f"ID: {user[0]} , Имя: {user[1]}")
    else:
        print("Пользователи не найдены.")
    cursor.close()
    conn.close()


# Удалить пользователя по ID
def delete_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Проверяем, существует ли пользователь
    cursor.execute("SELECT name FROM users WHERE id = %s;", (user_id,))
    user = cursor.fetchone()

    if not user:
        print(f"Пользователь с ID {user_id} не найден.")
    else:
        confirm = input(f"Удалить пользователя {user[0]} (ID {user_id})? (y/n): ")
        if confirm.lower() == 'y':
            cursor.execute("DELETE FROM users WHERE id = %s;", (user_id,))
            conn.commit()
            print(f"Пользователь {user[0]} удалён.")
        else:
            print("Удаление отменено.")

    cursor.close()
    conn.close()


# Основной обработчик команд
def main():
    parser = argparse.ArgumentParser(description="Управление пользователями в базе данных.")
    subparsers = parser.add_subparsers(dest='command')

    # Команда list
    subparsers.add_parser('list', help='Вывести всех пользователей')

    # Команда delete
    delete_parser = subparsers.add_parser('delete', help='Удалить пользователя по ID')
    delete_parser.add_argument('user_id', type=str, help='ID пользователя для удаления')

    args = parser.parse_args()

    if args.command == 'list':
        list_users()
    elif args.command == 'delete':
        delete_user(args.user_id)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
