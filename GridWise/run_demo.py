from pprint import pprint

from app.interpreter import interpret_notes


def main():
    operator_notes = [
        "Solar output will drop to about 20% from 1 PM to 3 PM.",
        "Do not charge the battery between 2 PM and 4 PM.",
        "The cafeteria menu changes tomorrow.",
    ]

    result = interpret_notes(
        operator_notes
    )

    print()
    print("=" * 70)
    print("GRIDWISE PERSON A - DEMO")
    print("=" * 70)
    print()

    pprint(
        result,
        sort_dicts=False
    )

    print()
    print("=" * 70)
    print("RESULT COUNT:", len(result))
    print("=" * 70)


if __name__ == "__main__":
    main()