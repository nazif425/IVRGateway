import sys, os, random, base64, hashlib, secrets, random, string, requests

from os import environ
from flask import Flask, request, jsonify, abort, render_template, Response, flash, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from sqlalchemy.sql import func
from models import db, User, CallSession
from fhir.resources.patient import Patient
from fhir.resources.humanname import HumanName
from datetime import date, datetime
import json

#Setup FLASK App
app = Flask(__name__)
app.debug = True
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:12345678@127.0.0.1:3306/ivr_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)
migrate = Migrate(app, db)
app.secret_key = b'\xb7\xc1q\x86\xd3\xf2{5`\xaek\xffV\xea\xf3\x80n\n\xa7\xcb\xc0\x95lo'

# Global data
ses_data = {
    "validated" : False,
    "patient_id" : "",
    "practitioner_id" : "",
    "data" : {
        'heart_rate': None,
        'systolic_blood_pressure': None,
        'diastolic_blood_pressure': None
    }
}


# OPENMRS
OPENMRS_BASE_URL = 'http://127.0.0.1:8081/openmrs'
OPENMRS_FHIR_VERSION = 'R4'
OPENMRS_FHIR_API = f'{OPENMRS_BASE_URL}/ws/fhir2/{OPENMRS_FHIR_VERSION}/'
bearer_token = 'Basic YWRtaW46QWRtaW4xMjM='

@app.before_request
def before_request_func():
    # Perform tasks before each request handling
    if request.values.get('isActive', None) == 0:
        clear_session_data()
        abort(200, "Session ended")
    sessionId = request.values.get('sessionId', None)
    if sessionId:
        session = CallSession.query.filter(CallSession.session_id==sessionId).first()
        if session:
            ses_data["data"] = session.data
            ses_data["validated"] = session.validated
            ses_data["practitioner_id"] = session.practitioner_id
            ses_data["patient_id"] = session.patient_id
        else:
            data = {
                "session_id" : request.values.get('sessionId', None),
                "validated" : ses_data["validated"],
                "data" : ses_data["data"],
                "practitioner_id" : ses_data["practitioner_id"],
                "patient_id" : ses_data["patient_id"]
            }
            db.session.add(CallSession(**data))
            db.session.commit()

@app.after_request
def after_request_func(response):
        # Perform tasks after each request handling
    sessionId = request.values.get('sessionId', None)
    if sessionId:
        session = CallSession.query.filter(CallSession.session_id==sessionId).first()
        if session:
            session.validated = ses_data["validated"]
            session.data = ses_data["data"]
            session.practitioner_id = ses_data["practitioner_id"]
            session.patient_id = ses_data["patient_id"]
            db.session.commit()
    return response

def cardio_data_collector():
    heart_rate = ses_data["data"].get('heart_rate', None)
    systolic_bp = ses_data["data"].get('systolic_blood_pressure', None)
    diastolic_bp = ses_data["data"].get('diastolic_blood_pressure', None)
    print(heart_rate, systolic_bp, diastolic_bp, sep=" ")
    if heart_rate is None:
        with open('standard_responses/heart_rate.xml') as f:
            response = f.read()
        return response
    elif systolic_bp is None:
        with open('standard_responses/systolic_blood_pressure.xml') as f:
            response = f.read()
        return response
    elif diastolic_bp is None:
        with open('standard_responses/diastolic_blood_pressure.xml') as f:
            response = f.read()
        return response
    else:
        response = '<Response>'
        response += f'<Say>Your provided heartrate is {heart_rate}</Say>'
        response += f'<Say>Your provided systolic blood pressure is {systolic_bp}</Say>'
        response += f'<Say>Your provided diastolic blood pressure is {diastolic_bp}</Say>'
        response += '<GetDigits timeout="30" finishOnKey="#" callbackUrl="https://nazif425.jprq.live/submit">'
        response += '<Say>If this is correct and you want to submit, press one followed by the hash sign. If you want to abort press two followed by the hash sign</Say>'
        response += '</GetDigits></Response>'

        return response

def verify_practitioner_id(id=None):
    if ses_data["validated"]:
        return True
    if id:
        response = requests.get(
            OPENMRS_FHIR_API + 'Practitioner?identifier=' + id,
            headers={
                "Authorization": bearer_token,
                "Content-Type": "application/fhir+json"
            })
        if response.status_code == 200:
            data = response.json()
            if data['total'] == 1:
                ses_data["validated"] = True
                ses_data["practitioner_id"] = data['entry'][0]['resource']['id']
                user = User(practitioner_id=ses_data["practitioner_id"], phone_number=request.values.get('callerNumber', None))
                db.session.add(user)
                db.session.commit()
                return True
    else:
        try:
            user = User.query.get(User.phone_number==request.values.get('callerNumber', None))
            ses_data["practitioner_id"] = user.practitioner_id
            ses_data["validated"] = True
        except:
            return False
    return False

def verify_patient_id(id):
    if id:
        response = requests.get(
            OPENMRS_FHIR_API + 'Patient?identifier=' + id,
            headers={
                "Authorization": bearer_token,
                "Content-Type": "application/fhir+json"
            })
        if response.status_code == 200:
            data = response.json()
            if data['total'] == 1:
                ses_data["patient_id"] = data['entry'][0]['resource']['id']
                return True
    return False


def create_encounter():
    current_time = datetime.now().strftime('%Y-%m-%d')

    with open(os.path.join("openmrs_fhir_templates", "encounter.json")) as json_file:
        data = json.load(json_file)
    
    data['subject']['reference'] = f"Patient/{ses_data['patient_id']}"
    data['period']['start'] = f"{current_time}"
    response = requests.post(
        OPENMRS_FHIR_API + 'Encounter/',
        json=data,
        headers={
            "Authorization": bearer_token,
            "Content-Type": "application/fhir+json"
        })
    if response.status_code == 201:
        data = response.json()
        return data['id']
    return None

def get_interpretation(observation_json):
    vital_ranges = {
        "5085AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA": {  # Systolic blood pressure
            "high": 120,
            "low": 90,
            "interpretations": {
                "H": "High",
                "L": "Low",
                "N": "Normal"
            }
        },
        "5086AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA": {  # Diastolic blood pressure
            "high": 80,
            "low": 60,
            "interpretations": {
                "H": "High",
                "L": "Low",
                "N": "Normal"
            }
        },
        "5087AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA": {  # Heart rate
            "high": 100,
            "low": 60,
            "interpretations": {
                "H": "High",
                "L": "Low",
                "N": "Normal"
            }
        }
    }
    
    value = observation_json.get("valueQuantity", {}).get("value", None)
    code = observation_json["code"]["coding"][0]["code"]
    if value is not None and code in vital_ranges:
        vital_range = vital_ranges[code]
        if int(value) > vital_range["high"]:
            return {
                "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
                "code": "H",
                "display": vital_range["interpretations"]["H"]
            }
        elif int(value) < vital_range["low"]:
            return {
                "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
                "code": "L",
                "display": vital_range["interpretations"]["L"]
            }
        else:
            return {
                "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
                "code": "N",
                "display": vital_range["interpretations"]["N"]
            }
    
    return None

def generate_observation_data_from_file(file_path, patient_id, encounter_id, value):
    current_time = datetime.now().strftime('%Y-%m-%d')

    with open(file_path) as json_file:
        data = json.load(json_file)

    data['subject']['reference'] = f"Patient/{patient_id}"
    data['encounter']['reference'] = f"Encounter/{encounter_id}"
    data['effectiveDateTime'] = current_time
    data['valueQuantity']['value'] = value
    data['interpretation'][0]["coding"][0] = get_interpretation(data)
    return data

def send_data_to_openmrs():
    file_path = 'openmrs_fhir_templates/'
    encounter_id = create_encounter()
    
    heart_rate = ses_data["data"].get('heart_rate', None)
    systolic_bp = ses_data["data"].get('systolic_blood_pressure', None)
    diastolic_bp = ses_data["data"].get('diastolic_blood_pressure', None)
    
    # store heart rate observation
    value = heart_rate
    observation_data = generate_observation_data_from_file(os.path.join(file_path, 'observation_heart_rate.json'),
                                                            ses_data["patient_id"], 
                                                            encounter_id, 
                                                            value)
    requests.post(OPENMRS_FHIR_API + 'Observation', json=observation_data, headers={'Content-Type': 'application/fhir+json',
                                                 'Authorization': bearer_token})
    
    # store systolic blood pressure observation
    value = systolic_bp
    observation_data = generate_observation_data_from_file(os.path.join(file_path, 'observation_systolic_blood_pressure.json'),
                                                            ses_data["patient_id"],
                                                            encounter_id,
                                                            value)
    requests.post(OPENMRS_FHIR_API + 'Observation', json=observation_data, headers={'Content-Type': 'application/fhir+json',
                                                 'Authorization': bearer_token})
    
    # store diastolic blood pressure
    value = diastolic_bp
    observation_data = generate_observation_data_from_file(os.path.join(file_path, 'observation_diastolic_blood_pressure.json'),
                                                            ses_data["patient_id"], 
                                                            encounter_id, 
                                                            value)
    requests.post(OPENMRS_FHIR_API + 'Observation', json=observation_data, headers={'Content-Type': 'application/fhir+json',
                                                 'Authorization': bearer_token})
""""""


def send_data_to_cedar():
    cedar_url = 'https://resource.metadatacenter.org/template-instances'
    cedar_api_key = 'apiKey 62838dcb5b6359a1a93baeeef907669813ec431437b168efde17a61c254b3355'
    current_time = datetime.now()

    cedar_template = open('cedar_template.json')
    data = json.load(cedar_template)
    data['PatientID']['@value'] = '1234' # TODO: Add patient ID request
    data['DataCollectedViaIVR']['@value'] = 'Yes'
    data['Date']['@value'] = current_time.strftime('%Y-%m-%d')
    data['Pulse Number']['@value'] = str(ses_data["data"]['heart_rate'])
    data['Blood Pressure (Systolic)']['@value'] = str(ses_data["data"]['systolic_blood_pressure'])
    data['Blood Pressure (Diastolic)']['@value'] = str(ses_data["data"]['diastolic_blood_pressure'])
    data['schema:name'] = f'PGHD {current_time.strftime("%d/%m/%Y %H:%M:%S")}'
    clear_session_data()

    requests.post(cedar_url, json=data, headers={'Content-Type': 'application/json',
                                                 'Accept': 'application/json',
                                                 'Authorization': cedar_api_key})

def clear_session_data():
    ses_data["validated"] = False
    ses_data["practitioner_id"] = ""
    ses_data["patient_id"] = ""
    ses_data["data"] = {
        'heart_rate': None,
        'systolic_blood_pressure': None,
        'diastolic_blood_pressure': None
    }
    sessionId = request.values.get('sessionId', None)
    if sessionId:
        session = CallSession.query.filter(CallSession.session_id==sessionId).first()
        if session:
            db.session.delete(session)
            db.session.commit()

@app.route("/pghd_handler", methods=['POST','GET'])
def pghd_handler():
    id = request.values.get("dtmfDigits", None)
    if verify_practitioner_id(id):
        with open('standard_responses/pghd_menu.xml') as f:
            response = f.read()
        return response
    if not id:
        with open('standard_responses/authentication.xml') as f:
            response = f.read()
        return response
    else:
        with open('standard_responses/failed_authentication.xml') as f:
            response = f.read()
        return response

@app.route("/pghd_cardio_handler", methods=['POST'])
def pghd_cardio_handler():
    digits = request.values.get("dtmfDigits", None)
    print(digits)
    if digits == '1':
        with open('standard_responses/get_patient_id.xml') as f:
            response = f.read()
        return response
    else:
        return '<Response><Reject/></Response>'

@app.route("/patient_id_handler", methods=['POST'])
def patient_id_handler():
    patient_id = request.values.get("dtmfDigits", None)
    if verify_patient_id(patient_id):
        return cardio_data_collector()
    else:
        with open('standard_responses/invalid_patient_id.xml') as f:
            response = f.read()
        return response

@app.route("/heart_rate", methods=['POST'])
def heart_rate():
    digits = request.values.get("dtmfDigits", None)
    if digits is not None:
        ses_data["data"]['heart_rate'] = digits

    return cardio_data_collector()


@app.route("/systolic_blood_pressure", methods=['POST'])
def systolic_blood_pressure():
    digits = request.values.get("dtmfDigits", None)
    if digits is not None:
        ses_data["data"]['systolic_blood_pressure'] = digits

    return cardio_data_collector()


@app.route("/diastolic_blood_pressure", methods=['POST'])
def diastolic_blood_pressure():
    digits = request.values.get("dtmfDigits", None)
    if digits is not None:
        ses_data["data"]['diastolic_blood_pressure'] = digits

    return cardio_data_collector()


@app.route("/submit", methods=['POST'])
def submit():
    digits = request.values.get("dtmfDigits", None)
    if digits == '1':
        # send_data_to_cedar()
        send_data_to_openmrs()
        clear_session_data()
        return '<Response><Say>Your data has been saved, thank you for your time</Say><Reject/></Response>'
    else:
        clear_session_data()
        return '<Response><Reject/></Response>'

if __name__ == '__main__':
    app.run(debug=True)
