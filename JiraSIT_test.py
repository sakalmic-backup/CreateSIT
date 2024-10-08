import getpass


def main():
    # Prompt for a basic username and password
    username = input("Enter your username: ")
    password = getpass.getpass("Enter your password (hidden): ")

    print(f"Username entered: {username}")
    print("Password entered, but hidden.", password)


if __name__ == "__main__":
    main()