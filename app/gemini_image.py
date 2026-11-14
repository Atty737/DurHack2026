from google import genai
from dotenv import load_dotenv
import json


def gemini_read_image(image_path):
    load_dotenv()
    client = genai.Client()

    file = client.files.upload(file=image_path)

    interaction = client.interactions.create(
        model="gemini-3.5-flash-lite",
        input=[
            {"type": "text", "text": "Return a list of json objects in format {\"item\":\"<item_name>\", \"quantity\":<item_quantity>, \"price\":<item_price>} Only count food items and ignore discounts. Do not include ``` or json. If the name is in all caps, capitalise the first letter of each word only. If a word is shortened, convert it into its longer version."},
            {
                "type": "image",
                "uri": file.uri,
                "mime_type": file.mime_type
            }
        ]
    )

    items = json.loads(interaction.output_text)

    for item in items:
        item["price"] = round(item["price"], 2) 

    return json.loads(interaction.output_text)