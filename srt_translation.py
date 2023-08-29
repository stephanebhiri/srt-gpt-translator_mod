import re
import openai
from tqdm import tqdm
import os
import json
import argparse
import configparser
import chardet

# Read configuration
with open('settings.cfg', 'rb') as f:
    content = f.read()
    encoding = chardet.detect(content)['encoding']
    
with open('settings.cfg', encoding=encoding) as f:
    config_text = f.read()
    config = configparser.ConfigParser()
    config.read_string(config_text)

openai_apikey = config.get('option', 'openai-apikey')
language_name = config.get('option', 'target-language')
openai.api_key = openai_apikey

# Parse command-line arguments
parser = argparse.ArgumentParser()
parser.add_argument("filename", help="Name of the input file")
parser.add_argument("-t", "--tone", help="Tone of the translation", choices=['formal', 'informal'], default='informal')
parser.add_argument("--test", help="Only translate the first 3 short texts", action="store_true")
args = parser.parse_args()

filename = args.filename
base_filename, file_extension = os.path.splitext(filename)
new_filenametxt = base_filename + "_translated.srt"
new_filenametxt2 = base_filename + "_translated_bilingual.srt"
jsonfile = base_filename + "_process.json"
tone = args.tone

# Load previously translated text
translated_dict = {}
try:
    with open(jsonfile, "r", encoding="utf-8") as f:
        translated_dict = json.load(f)
except FileNotFoundError:
    pass

# Function to split text into blocks
def split_text(text):
    blocks = re.split(r'(\n\s*\n)', text)
    short_text_list = []
    short_text = ""
    for block in blocks:
        if len(short_text + block) <= 1024:
            short_text += block
        else:
            short_text_list.append(short_text)
            short_text = block
    short_text_list.append(short_text)
    return short_text_list

# Function to check if translation is valid
def is_translation_valid(original_text, translated_text):
    def get_index_lines(text):
        lines = text.split('\n')
        index_lines = [line for line in lines if re.match(r'^\d+$', line.strip())]
        return index_lines

    original_index_lines = get_index_lines(original_text)
    translated_index_lines = get_index_lines(translated_text)

    return original_index_lines == translated_index_lines

# Function to translate text
def translate_text(text, tone):
    max_retries = 3
    retries = 0
    tone_instruction = "using a formal tone" if tone == 'formal' else ""
    
    while retries < max_retries:
        try:
            completion = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "user",
                        "content": f"Translate the following subtitle text into {language_name} {tone_instruction}, but keep the subtitle number and timeline unchanged: \n{text}",
                    }
                ],
            )
            t_text = (
                completion["choices"][0]
                .get("message")
                .get("content")
                .encode("utf8")
                .decode()
            )
            
            if is_translation_valid(text, t_text):
                return t_text
            else:
                retries += 1
                print(f"Invalid translation format. Retrying ({retries}/{max_retries})")
        
        except Exception as e:
            import time
            sleep_time = 60
            time.sleep(sleep_time)
            retries += 1
            print(e, f"will sleep {sleep_time} seconds, Retrying ({retries}/{max_retries})")

    print(f"Unable to get a valid translation after {max_retries} retries. Returning the original text.")
    return text

# Function to translate and store text
def translate_and_store(text, tone):
    if text in translated_dict:
        return translated_dict[text]

    translated_text = translate_text(text, tone)
    translated_dict[text] = translated_text

    with open(jsonfile, "w", encoding="utf-8") as f:
        json.dump(translated_dict, f, ensure_ascii=False, indent=4)

    return translated_text 

# Main script
text = ""

if filename.endswith('.srt'):
    with open(filename, 'r', encoding='utf-8') as file:
        text = file.read()
else:
    print("Unsupported file type")

short_text_list = split_text(text)
if args.test:
    short_text_list = short_text_list[:3]

translated_text = ""

for short_text in tqdm(short_text_list):
    translated_short_text = translate_and_store(short_text, tone)
    translated_text += f"{translated_short_text}\n\n"

def replace_text(text1, text2):
    def split_blocks(text):
        blocks = re.split(r'(\n\s*\n)', text.strip())
        return [block.split('\n') for block in blocks if block.strip()]

    blocks1 = split_blocks(text1)
    blocks2 = split_blocks(text2)

    replaced_lines = []

    for block1, block2 in zip(blocks1, blocks2):
        replaced_lines.extend(block1[:2])
        replaced_lines.extend(block2[2:])
        replaced_lines.append('')

    return '\n'.join(replaced_lines).strip()

def merge_text(text1, text2):
    def split_blocks(text):
        blocks = re.split(r'(\n\s*\n)', text.strip())
        return [block.split('\n') for block in blocks if block.strip()]

    blocks1 = split_blocks(text1)
    blocks2 = split_blocks(text2)

    merged_lines = []

    for block1, block2 in zip(blocks1, blocks2):
        merged_lines.extend(block1[:2])
        merged_lines.extend(block1[2:])
        merged_lines.extend(block2[2:])
        merged_lines.append('')

    return '\n'.join(merged_lines).strip()

result = replace_text(text, translated_text)

with open(new_filenametxt, "w", encoding="utf-8") as f:
    f.write(result)

result2 = merge_text(text, translated_text)

with open(new_filenametxt2, "w", encoding="utf-8") as f:
    f.write(result2)

try:
    os.remove(jsonfile)
    print(f"File '{jsonfile}' has been deleted.")
except FileNotFoundError:
    print(f"File '{jsonfile}' not found. No file was deleted.")
