import re


def word_in_text(text, keywords):
    #print("text", text)
    t = text.lower()
    words = re.findall(r"\b\w+\b", t)
    for kw in keywords:
        if " " in kw:  # phrase
            if kw.lower() in t:
                return True
        elif kw.lower() in words:
            return True
    return False