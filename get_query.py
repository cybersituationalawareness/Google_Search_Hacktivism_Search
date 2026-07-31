def get_query(key_word_txt):

    with open(key_word_txt, 'r', encoding='utf-8') as file:
        lines = [line.strip() for line in file if line.strip()]

    return lines