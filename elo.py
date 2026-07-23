def calculate(winner_elo, loser_elo, score):

    expected = 1 / (
        1 + 10 ** ((loser_elo - winner_elo) / 400)
    )

    change = 50 * (1 - expected)

    if score == "2-0":
        change *= 1.2

    elif score == "3-0":
        change *= 1.3

    return round(change)