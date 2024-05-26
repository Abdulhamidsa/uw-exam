from bottle import get, template, static_file, response
import x  # Assuming 'x' is your database client for ArangoDB
from icecream import ic  # For debugging output
import requests  # To make HTTP requests
import json  # For JSON handling
from dotenv import load_dotenv  # To load environment variables from a .env file
import os  # For operating system interactions

##############################

# Load environment variables from a .env file
load_dotenv('.env')
username = os.getenv('username')
token = os.getenv('token')

##############################

# CHECK TOKEN IF MATCH
def check_token(username, token):
    # Make a GET request to check the validity of the token
    response = requests.get(
        f'https://www.pythonanywhere.com/api/v0/user/{username}/cpu/',
        headers={'Authorization': f'Token {token}'}
    )
    return response.status_code  # Return the status code of the response

################################

# END POINTS - GET REQUEST
@get("/")
def _():
    # Print a debug message and return a confirmation string that the backend is running
    ic("xxxxxxx")
    return "BACKEND RUNNING READY FOR REQUESTS "

################################

@get("/get-crimes")
def _():
    # Query to fetch all crimes from the 'crimes' collection
    query = {
        "query": """
            FOR crime IN crimes
    LET criminal = (
        FOR edge IN crime_criminal_edges
            FILTER edge._from == CONCAT('crimes/', crime._key)
            FOR criminal IN criminals
                FILTER criminal._key == PARSE_IDENTIFIER(edge._to).key
                RETURN criminal
    )
    RETURN MERGE(crime, { criminal: FIRST(criminal) })

        """
    }
    res = x.db(query)  # Execute the query using the database client
    if res["error"] == False:
        # Set response headers to allow cross-origin requests
        # response.headers["Access-Control-Allow-Origin"] = "*" 
        # response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"  
        # response.headers["Access-Control-Allow-Headers"] = "Origin, Accept, Content-Type, X-Requested-With, X-CSRF-Token"  
        response.content_type = "application/json"
        # Return the query results as JSON
        return json.dumps(res["result"])
    else:
        # Print an error message if the query fails
        print("Error fetching crimes. Error message:", res["errorMessage"])
        return "Error fetching crimes"

##############################

def transactionQuery(crimes, criminals, associates):
    crimesInsert = ""
    for i, crime in enumerate(crimes):
            # Convert victims to a JSON-compatible string
            victims = json.dumps(crime.get('crime_victims', []))

            crimesInsert += f'''
            var crime{i} = db.crimes.firstExample({{"_key": "{crime['_key']}"}})
            if (crime{i} == null) {{
                crime{i} = db.crimes.save({{
                    _key: "{crime['_key']}",
                    "crime_type": "{crime['crime_type']}",
                    "crime_city": "{crime['crime_city']}",
                    "crime_committed_at": "{crime['crime_committed_at']}",
                    "crime_description": "{crime['crime_description']}",
                    "crime_severity": {crime['crime_severity']},
                    "crime_location": {{"latitude": {crime['crime_location']['latitude']}, "longitude": {crime['crime_location']['longitude']}}},
                    "crime_report_time": "{crime['crime_report_time']}",
                    "crime_victims": {victims}
                }})
            }}
            '''


    criminalsInsert = ""
    for i, criminal in enumerate(criminals):
        criminalsInsert += f'''
        var criminal{i} = db.criminals.firstExample({{"_key": "{criminal['_key']}"}})
        if (criminal{i} == null) {{
            criminal{i} = db.criminals.save({{
                _key: "{criminal['_key']}",
                "id": "{criminal['id']}",
                "first_name": "{criminal['first_name']}",
                "last_name": "{criminal['last_name']}",
                "age": {criminal['age']},
                "city": "{criminal['city']}",
                "location": {{"latitude": {criminal['location']['latitude']}, "longitude": {criminal['location']['longitude']}}},
                "avatar": "{criminal['avatar']}",
                "type": "criminal",
                "crime_type": "{criminal['crime_type']}",
                "crime_id": "{criminal['crime_id']}"
            }})
        }}
        '''

    associatesInsert = ""
    for i, associate in enumerate(associates):
        associatesInsert += f'''
        var associate{i} = db.associates.firstExample({{"_key": "{associate['_key']}"}})
        if (associate{i} == null) {{
            associate{i} = db.associates.save({{
                _key: "{associate['_key']}",
                "id": "{associate['id']}",
                "first_name": "{associate['first_name']}",
                "last_name": "{associate['last_name']}",
                "age": {associate['age']},
                "city": "{associate['city']}",
                "location": {{"latitude": {associate['location']['latitude']}, "longitude": {associate['location']['longitude']}}},
                "avatar": "{associate['avatar']}",
                "criminal_history": "{associate['criminal_history']}"
            }})
        }}
        '''

    # Insert edges to connect crimes and criminals based on shared crime_id, with type 'perpetrator'
    edgesInsertCriminals = ""
    for i, criminal in enumerate(criminals):
        edgesInsertCriminals += f'''
        var edge{i} = db.crime_criminal_edges.firstExample({{"_from": "crimes/{criminal['crime_id']}", "_to": "criminals/{criminal['_key']}"}})
        if (edge{i} == null) {{
            db.crime_criminal_edges.save({{
                _from: "crimes/{criminal['crime_id']}",
                _to: "criminals/{criminal['_key']}",
                "type": "perpetrator"
            }})
        }}
        '''



    edgesInsertSuspects = ""
    for criminal in criminals:
        for associate in associates:
            if criminal['city'] == associate['city'] and 20 <= criminal['age'] <= 30 and 20 <= associate['age'] <= 30:
                relationship_type = "family" if criminal['last_name'] == associate['last_name'] else "potential suspect"
                edgesInsertSuspects += f'''
                db.criminal_associate_edges.save({{
                    _from: "criminals/{criminal['_key']}",
                    _to: "associates/{associate['_key']}",
                    "type": "{relationship_type}"
                }})
                '''
    query = {
        "collections": {
            "write": ["criminals", "crimes", "associates", "crime_criminal_edges", "criminal_associate_edges"]
        },
        "action": f"""
        function () {{
            var db = require('@arangodb').db;
            {crimesInsert}
            {criminalsInsert}
            {associatesInsert}
            {edgesInsertSuspects}
            {edgesInsertCriminals}
            return "success!";
        }}
        """

    }
    return x.db(query, "transaction")

################################################################

@get('/insert-crimes')
def get_crimes():
    # Check token validity
    if check_token(username, token) == 200:
        # Fetch crimes data from an external source
        crimes_response = requests.get('https://abdulhamidsa.pythonanywhere.com/crimes')
        if crimes_response.status_code == 200:
            # Extract JSON data from the response
            crimes_data = crimes_response.json()
            criminals_data = []  # List to store criminals data
            associates_data = []  # List to store associates data
            crimes_list = []  # List to store crimes data

            if crimes_data:
                for crime in crimes_data:
                    # Extract victims data
                    victims = crime.get('crime_victims', [])
                    
                    # Append crime details to the crimes_list
                    crimes_list.append({
                        "_key": crime['crime_id'],
                        "crime_type": crime['crime_type'],
                        "crime_city": crime['crime_city'],
                        "crime_committed_at": crime['crime_committed_at'],
                        "crime_description": crime['crime_description'],
                        "crime_severity": crime['crime_severity'],
                        "crime_location": {"latitude": crime['crime_location']['latitude'], "longitude": crime['crime_location']['longitude']},
                        "crime_report_time": crime['crime_report_time'],
                        "crime_victims": victims  # Include victims' data
                    })


                    if crime['crime_perpetrator']:
                        crime['crime_perpetrator']['type'] = 'criminal'
                        crime['crime_perpetrator']['crime_type'] = crime['crime_type']  # Add the crime type to the criminal
                        criminals_data.append({
                            "_key": crime['crime_perpetrator']['id'],
                            "id": crime['crime_perpetrator']['id'],
                            "first_name": crime['crime_perpetrator']['first_name'],
                            "last_name": crime['crime_perpetrator']['last_name'],
                            "age": crime['crime_perpetrator']['age'],
                            "city": crime['crime_perpetrator']['city'],
                            "location": {"latitude": crime['crime_perpetrator']['location']['latitude'], "longitude": crime['crime_perpetrator']['location']['longitude']},
                            "avatar": crime['crime_perpetrator']['avatar'],
                            "type": "criminal",
                            "crime_type": crime['crime_type'],
                            "crime_id": crime['crime_id']
                        })

                    if crime.get('crime_associates'):
                        for associate in crime['crime_associates']:
                            associates_data.append({
                                "_key": associate['id'],
                                "id": associate['id'],
                                "first_name": associate['first_name'],
                                "last_name": associate['last_name'],
                                "age": associate['age'],
                                "city": associate['city'],
                                "location": {"latitude": associate['location']['latitude'], "longitude": associate['location']['longitude']},
                                "avatar": associate['avatar'],
                                "criminal_history": associate['criminal_history']
                            })

                # Call the transactionQuery function to insert data into the database
                result = transactionQuery(crimes_list, criminals_data, associates_data)
                return result
            else:
                response.status = 400
                return json.dumps({"error": "No crime data found."})
        else:
            response.status = crimes_response.status_code
            return json.dumps({"error": "Failed to fetch crime data."})
    else:
        response.status = 401
        return json.dumps({"error": "Token is invalid."})
##############################
@get('/get-potential-suspects/<criminal_id>')
def get_potential_suspects(criminal_id):
    # Query to find potential suspects related to a criminal
    query = f"""
        LET criminal_custom_id = "{criminal_id}"
        FOR criminal IN criminals
            FILTER criminal.id == criminal_custom_id
            FOR v, e, p IN OUTBOUND criminal._id criminal_associate_edges
                RETURN v
        """
    payload = {
        "query": query
    }
    response = x.db(payload)  # Execute the query
    if not response.get("error"):
        return response  # Return the response if the query is successful
    else:
        # Raise an exception if the query fails
        raise Exception(f"Query failed with error message: {response.get('errorMessage')}")
