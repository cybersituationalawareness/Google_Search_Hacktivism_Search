import io
import time
import pytesseract
from PIL import Image
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from ollama import Client
from stanza.pipeline.coref_processor import extract_text
from datetime import datetime
from typing import List, Literal
from pydantic import BaseModel, Field

def transform_date_time_string(raw_data):

    # 1. Clean the string (remove the dot and extra space)
    clean_data = raw_data.replace("· ", "")

    # 2. Parse into a datetime object
    dt_object = datetime.strptime(clean_data, "%I:%M %p %b %d, %Y")

    # 3. Format to dd/mm/yyyy
    formatted_date = dt_object.strftime("%m/%d/%Y")

    #print(f"Formatted Date: {formatted_date}")

    return  formatted_date

# 1. Point to your Tesseract installation
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'


def get_text_from_slow_site(url):

    print("OCR..ing!!!")

    chrome_options = Options()
    chrome_options.add_argument("--headless")
    driver = webdriver.Chrome(options=chrome_options)

    try:
        driver.get(url)

        # 2. Wait for the page to signal it is "Ready"
        WebDriverWait(driver, 30).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )


        # 3. Optional: Extra buffer for heavy JavaScript/Animations
        time.sleep(2)

        #xpath_val = "//*[@id='react-root']/div/div/div[2]/main/div/div/div/div/div/section/div/div/div[1]/div/div/article/div/div/div[3]/div[3]/div/div[1]/div/div[1]/a/time"

        element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//time"))
        )

        try:
            date = transform_date_time_string(element.text)
        except ValueError:
            date = element.text

        # 4. OCR Process
        screenshot_bytes = driver.get_screenshot_as_png()
        image = Image.open(io.BytesIO(screenshot_bytes))

        # Pro Tip: Convert to Greyscale to help Tesseract read better
        text = pytesseract.image_to_string(image.convert('L'))

        driver.quit()

        return date, text

    except Exception as e:

        return "Error"

        driver.quit()

    finally:
        driver.quit()


#get_text_from_slow_site("https://x.com/FalconFeedsio/status/2042533349391241302")