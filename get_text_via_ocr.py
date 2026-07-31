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


client = Client(host='http://127.0.0.1:11434')

AviationType = Literal[
    "Airport",
    "Airline",
    "Aerospace & Defence",
    "Aviation Body",
    "Air Navigation",
    "Transport Body",
    "Aviation Service"
]

OLLAMA_MODEL_NAME = 'llama3:latest'


######################Class Model######################

class Attacker(BaseModel):
    attacker: str

class AviationEntity(BaseModel):
    name: str = Field(description="The name of the organization or company")
    entity_type: AviationType = Field(description="The specific category of the aviation entity")

class AviationReport(BaseModel):
    organizations: List[AviationEntity]

class GeographicInfo(BaseModel):
    country: str = Field(description="The full name of the country extracted from the text.")
    region: Literal["EMEA", "APAC", "AMER"] = Field(
        description="The geographic region the country belongs to. EMEA (Europe, Middle East, Africa), APAC (Asia-Pacific), or AMER (Americas)."
    )

class CountryExtraction(BaseModel):
    data: GeographicInfo

######################Class Model Functions######################

def get_attacker_data(text: str):
    prompt = f"""
        Analyze the following text and extract the attacker. {text}
        """

    # 3. Use the client instance with the Pydantic schema
    response = client.chat(
        model=OLLAMA_MODEL_NAME,
        messages=[{'role': 'user', 'content': prompt}],
        format=Attacker.model_json_schema(),
        options={'temperature': 0}
    )

    # 4. Parse the JSON string into the Pydantic object
    try:
        content = response['message']['content']

        return Attacker.model_validate_json(content)
    except Exception as e:
        print(f"Parsing error: {e}")
        return None


def extract_geo_data(text: str):
    # The prompt tells the model to extract AND classify
    prompt = f"""
    Extract the country from the following text and determine its global region 
    (EMEA, APAC, or AMER).

    Text: {text}
    """

    response = client.chat(
        model=OLLAMA_MODEL_NAME,
        messages=[{'role': 'user', 'content': prompt}],
        format=CountryExtraction.model_json_schema(),
        options={'temperature': 0}  # Critical for consistent classification
    )

    try:
        content = response['message']['content']
        # This parses the string into the Pydantic object
        result = CountryExtraction.model_validate_json(content)
        return result.data
    except Exception as e:
        print(f"Error: {e}")
        return None


def get_aviation_data(text: str):
    prompt = f"""
    Analyze the following text and extract aviation-related organizations.
    For each entity, classify it into one of the allowed types.
    Text: {text}
    """

    response = client.chat(
        model=OLLAMA_MODEL_NAME,
        messages=[{'role': 'user', 'content': prompt}],
        # Use the new schema
        format=AviationReport.model_json_schema(),
        options={'temperature': 0} # Keep it at 0 for consistent classification
    )

    try:
        content = response['message']['content']
        # This will now return an object with a list of classified entities
        return AviationReport.model_validate_json(content)
    except Exception as e:
        print(f"Classification error: {e}")
        return None

######################Class Model Functions######################


def transform_date_time_string(raw_data):

    # 1. Clean the string (remove the dot and extra space)
    clean_data = raw_data.replace("· ", "")

    # 2. Parse into a datetime object
    dt_object = datetime.strptime(clean_data, "%I:%M %p %b %d, %Y")

    # 3. Format to dd/mm/yyyy
    formatted_date = dt_object.strftime("%m/%d/%Y")

    #print(f"Formatted Date: {formatted_date}")

    return  formatted_date

"""
def prompt_llm(prompt):
    # Manually specify the host if 'localhost' isn't resolving

    try:
        response = client.chat(model='llama3:latest', messages=[
            {'role': 'user', 'content': prompt},
            ])

        response_text = response['message']['content']

        return response_text

    except Exception as e:
        print(f"Error: {e}")
        return e
"""

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

        #prompt0 = f'output only the threat actor:\n\n{text}'
        #prompt1 = f'output only the organizations from the following text and tag "aviation" if organisation is aviation related without explanation:\n\n{text}'
        #prompt2 = f'Identify the type of the aviation related organizations from the following text and output only either "Airport" or "Aviation Body" or "Aerospace & Defence" without explanation:\n\n{text} '
        #prompt3 = f'output only the targeted country from the following text without explanation:\n\n{text} '
        #prompt4 = f'Identify the region of the targeted country from the following text and output only either "AMER" or "EMEA" or "APAC" without explanation:\n\n{text}'


        #prompt_list = [prompt0, prompt1, prompt2, prompt3,prompt4]

        #response_list = []

        #for prompt in prompt_list:

        #    response = prompt_llm(prompt)

        #    response_list.append(response)

        attacker = get_attacker_data(text)
        org_info = get_aviation_data(text)
        geo_info = extract_geo_data(text)

        attacker_name = attacker.attacker if attacker else ""
        organizations = ", ".join(
            [entity.name for entity in org_info.organizations]) if org_info and org_info.organizations else ""
        aviation_entities = ", ".join(
            [entity.entity_type for entity in org_info.organizations]) if org_info and org_info.organizations else ""
        country = geo_info.country if geo_info else ""
        region = geo_info.region if geo_info else ""

        print(attacker_name)
        print(organizations)
        print(aviation_entities)
        print(country)
        print(region)

        return date, attacker_name, organizations, aviation_entities, country, region

    except Exception as e:

        return date, ["error", "error", "error", "error"]

        driver.quit()

    finally:
        driver.quit()


#get_text_from_slow_site("https://x.com/FalconFeedsio/status/2042533349391241302")