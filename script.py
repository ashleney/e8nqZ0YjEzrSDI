import argparse
import email
import email.header
import pathlib
import re
import traceback

import pymupdf
import tqdm


def decode_email_header(encoded_header: str) -> str:
    return str(email.header.make_header(email.header.decode_header(encoded_header)))


def is_ico(number: str) -> bool:
    if not number.isdigit() or len(number) != 8:
        return False

    n = [int(i) for i in number]
    return (11 - ((8 * n[0] + 7 * n[1] + 6 * n[2] + 5 * n[3] + 4 * n[4] + 3 * n[5] + 2 * n[6]) % 11)) % 10 == n[7]


def contains_cestne_prohlaseni(text: str) -> bool:
    return any(x in text.lower() for x in ("cestne prohlaseni", "čestné prohlášení", "čestně prohlašuji", "čestného prohlášení", "čestném prohlášením", "čestným prohlášením"))


def extract_icos(text: str) -> list[str]:
    numbers = [number.replace(" ", "") for number in re.findall(r"[0-9 ]+", text)]
    return [number for number in numbers if number != "45245053" and is_ico(number)]


def analyze_email(path: pathlib.Path) -> list[str]:
    with path.open("rb") as file:
        message = email.message_from_bytes(file.read())

    is_cestne_prohlaseni: bool = False
    icos: list[str] = []

    subject = decode_email_header(message["Subject"])

    icos += extract_icos(subject)
    if contains_cestne_prohlaseni(subject):
        is_cestne_prohlaseni = True

    for part in message.walk():
        content_type = part.get_content_type()
        filename = part.get_filename()
        if filename is not None:
            icos += extract_icos(filename)
            if contains_cestne_prohlaseni(filename):
                is_cestne_prohlaseni = True

        if content_type in ("application/pdf", "application/msword") or "document" in content_type or content_type.startswith("image"):
            try:
                payload = part.get_payload(decode=True)
                assert isinstance(payload, bytes)
                document = pymupdf.Document(filename=filename, stream=payload)
                for page in document:
                    text = page.get_text()

                    icos += extract_icos(text)
                    if contains_cestne_prohlaseni(text):
                        is_cestne_prohlaseni = True
            except Exception as e:
                traceback.print_exception(e)


        elif content_type in ("text/plain", "text/html"):
            payload = part.get_payload(decode=True)
            assert isinstance(payload, bytes)

            for encoding in ("utf-8", "cp852", "iso88592", "windows1250"):
                try:
                    text = payload.decode(encoding)
                    icos += extract_icos(text)
                    if contains_cestne_prohlaseni(text):
                        is_cestne_prohlaseni = True
                except (LookupError, UnicodeDecodeError):
                    pass

    if is_cestne_prohlaseni:
        return list(set(icos))
    else:
        return []


parser = argparse.ArgumentParser()
parser.add_argument("input", nargs="?", default="eml")
parser.add_argument("output", nargs="?", default="result.csv")

args = parser.parse_args()

result: list[tuple[str, str]] = []
for path in tqdm.tqdm(list(pathlib.Path(args.input).iterdir())):
    if path.suffix != ".eml":
        continue

    try:
        email_id = path.with_suffix("").name
        icos = analyze_email(path)
    except Exception as e:
        traceback.print_exception(e)
    else:
        result += [(email_id, ico) for ico in icos]

with open(args.output, "w") as file:
    file.write("id,ico\n" + "\n".join(",".join(x) for x in result))
