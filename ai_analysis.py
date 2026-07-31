import configparser
from pydantic import BaseModel, Field
from typing import List, Literal
import ollama
from datetime import datetime

client = ollama.Client(host='http://127.0.0.1:11434')
OllamaModel = "llama3:latest"


Motivation_Lit = Literal[
    "Financial Gain",
    "Espionage",
    "Hacktivism",
    "Disruption",
]

DirectImpact_Lit = Literal[
    "Website Outage",
    "System Outage",
    "Data Breach",
    "No Impact",
    "Not Reported",
    "Network Outage",
    "Malware Infection",
    "Espionage",
    "Email System Outage",
    "Security vulnerability",
]

AttackType_Lit = Literal[
    "Ransomware",
    "DDoS",
    "Data Breach",
    "Supply Chain Attack",
    "Web Attack",
    "Malware",
    "Phishing",
    "Espionage",
    "GPS Spoofing",
    "Security vulnerability",
    "Not reported"
]

AviationType = Literal[
    "Airport",
    "Airline",
    "Aerospace & Defence",
    "Aviation Body",
    "Air Navigation",
    "Transport Body",
    "Aviation Service"
    "Not reported"
]

# --- Keyword Matching ---
AVIATION_KEYWORDS = [
    "aviation", "airline", "airport", "aerospace", "aeronautical",
    "air traffic", "airbus", "boeing", "embraer"
]


class Motivation(BaseModel):
    Motivation: Motivation_Lit = Field(
        description="Impact of cyber incident"
    )


class DirectImpact(BaseModel):
    Direct_Impact: DirectImpact_Lit = Field(
        description="Impact of cyber incident"
    )


class AttackType(BaseModel):
    Attack_Type: AttackType_Lit = Field(
        description="The type of cyber incident"
    )


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


def date_transform(dt_str):
    published_date = dt_str
    if isinstance(dt_str, datetime):
        date_only = published_date.date()
        year = published_date.year
        quarter = (published_date.month - 1) // 3 + 1
    else:
        # Fallback if it's not a datetime object
        date_only = ""
        year = ""
        quarter = 1

    quarter_str = f"Q{quarter} {year}" if year else ""
    return date_only, year, quarter_str


def identify_motivation(text: str):
    prompt = f"""
    Identify the motivation of cyber incident
    (Financial Gain, Espionage, Hacktivism, Disruption).

    Text: {text}
    """
    try:
        response = client.chat(
            model=OllamaModel,
            messages=[{'role': 'user', 'content': prompt}],
            format=Motivation.model_json_schema(),
            options={'temperature': 0}
        )
        content = response['message']['content']
        result = Motivation.model_validate_json(content)
        return result.Motivation
    except Exception as err:
        print(f"Error classifying motivation: {err}")
        return None


def identify_direct_impact(text: str):
    prompt = f"""
    Identify the impact of cyber incident
    (Website Outage, System Outage, Data Breach, No Impact, Not Reported, Network Outage, Malware Infection, 
    Espionage, Email System Outage, Security vulnerability).

    Text: {text}
    """
    try:
        response = client.chat(
            model=OllamaModel,
            messages=[{'role': 'user', 'content': prompt}],
            format=DirectImpact.model_json_schema(),
            options={'temperature': 0}
        )
        content = response['message']['content']
        result = DirectImpact.model_validate_json(content)
        return result.Direct_Impact
    except Exception as err:
        print(f"Error classifying direct impact: {err}")
        return None


def identify_attack_type(text: str):
    prompt = f"""
    Identify the type of cyber incident
    (Ransomware, DDoS, Data Breach, Supply Chain Attack, Web Attack, Malware, Phishing, Espionage, 
    GPS Spoofing, Security vulnerability, Not reported).

    Text: {text}
    """
    try:
        response = client.chat(
            model=OllamaModel,
            messages=[{'role': 'user', 'content': prompt}],
            format=AttackType.model_json_schema(),
            options={'temperature': 0}
        )
        content = response['message']['content']
        result = AttackType.model_validate_json(content)
        return result.Attack_Type
    except Exception as err:
        print(f"Error classifying attack type: {err}")
        return None


def get_attacker_data(text: str):
    prompt = f"""
        Analyze the following text and extract the attacker. {text}
        """
    try:
        response = client.chat(
            model=OllamaModel,
            messages=[{'role': 'user', 'content': prompt}],
            format=Attacker.model_json_schema(),
            options={'temperature': 0}
        )
        content = response['message']['content']
        return Attacker.model_validate_json(content)
    except Exception as err:
        print(f"Error extracting attacker: {err}")
        return None


def extract_geo_data(text: str):
    prompt = f"""
    Extract the country from the following text and determine its global region 
    (EMEA, APAC, or AMER).

    Text: {text}
    """
    try:
        response = client.chat(
            model=OllamaModel,
            messages=[{'role': 'user', 'content': prompt}],
            format=CountryExtraction.model_json_schema(),
            options={'temperature': 0}
        )
        content = response['message']['content']
        result = CountryExtraction.model_validate_json(content)
        return result.data
    except Exception as err:
        print(f"Error extracting geo data: {err}")
        return None


def get_aviation_data(text: str):
    prompt = f"""
    Analyze the following text and extract aviation-related organizations.
    For each entity, classify it into one of the allowed types.
    Text: {text}
    """
    try:
        response = client.chat(
            model=OllamaModel,
            messages=[{'role': 'user', 'content': prompt}],
            format=AviationReport.model_json_schema(),
            options={'temperature': 0}
        )
        content = response['message']['content']
        return AviationReport.model_validate_json(content)
    except Exception as err:
        print(f"Error extracting aviation data: {err}")
        return None


def parse_rss_date(date_str):
    """Parses the RSS pubDate string into a date object."""
    if not date_str or date_str == 'N/A':
        return None
    try:
        return datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %Z").date()
    except ValueError:
        return None


def is_aviation_cyber_incident(title: str) -> bool:
    """
    Uses Ollama (llama3:8b) to determine if a title is related to an aviation cyber incident.
    Returns True if it is, False otherwise.
    """
    prompt = f"""
    <|begin_of_text|><|start_header_id|>system<|end_header_id|>
    You are a cybersecurity analyst specializing in aviation threat intelligence. Your task is to classify Hacktivism.

    CRITERIA:
    1. Must relate to AVIATION (Airlines, Airports, ATC, Boeing/Airbus, Aircraft systems).
    2. Must relate to Hacktivism (Ransomware, DDoS, Breach, Hacking, Phishing, Malware).

    OUTPUT FORMAT:
    Reasoning: [One sentence explaining why]
    Match: [YES or NO]
    <|eot_id|><|start_header_id|>user<|end_header_id|>


    CURRENT TITLE TO ANALYZE:
    {title}
    <|eot_id|><|start_header_id|>assistant<|end_header_id|>
    """
    try:
        response = client.chat(
            model=OllamaModel,
            messages=[{'role': 'user', 'content': prompt}],
        )
        content = response['message']['content'].strip().upper()
        return "YES" in content
    except Exception as e:
        print(f"Error querying Ollama: {e}")
        # Default to False if the AI fails
        return False


def date_transform(dt_str):
    published_date = dt_str
    if isinstance(dt_str, datetime):
        #date_only = published_date.date()
        year = published_date.year
        quarter = (published_date.month - 1) // 3 + 1
    else:
        # Fallback if it's not a datetime object
        date_only = ""
        year = ""
        quarter = 1

    quarter_str = f"Q{quarter} {year}" if year else ""
    return year, quarter_str