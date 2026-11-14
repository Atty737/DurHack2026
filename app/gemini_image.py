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
            {"type": "text", "text": "Return a list of json objects in format {\"item\":\"<item_name>\", \"quantity\":<item_quantity>, \"price\":<item_price>} Only count food items and ignore discounts. Do not include ``` or json."},
            {
                "type": "image",
                "uri": file.uri,
                "mime_type": file.mime_type
            }
        ]
    )

    return json.loads(interaction.output_text)

print(gemini_read_image("irl_sample.jpeg"))