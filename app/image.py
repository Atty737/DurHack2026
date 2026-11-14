import cv2
import pytesseract
import matplotlib.pyplot as plt
from pytesseract import Output

image_path = "image.jpg"

image = cv2.imread(image_path)

if image is None:
    raise FileNotFoundError(
        f"Unable to load image: {image_path}"
    )

image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)