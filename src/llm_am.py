import ollama
import json
from xaif_eval import xaif
from itertools import combinations
import logging
import re

logging.basicConfig(datefmt='%H:%M:%S',
                    level=logging.DEBUG)


class LLMArgumentStructure:
    def __init__(self,file_obj):
        self.file_obj = file_obj

        self.file_obj = file_obj
        self.f_name = file_obj.filename
        self.file_obj.save(self.f_name)
        file = open(self.f_name,'r')

        xAIF_input = self.get_aif()  
        self.aif_obj = xaif.AIF(xAIF_input)

    def llm_model(self, prompt, model_name="deepseek-r1:1.5b"):
        """Run deepseek-r1:7b model with a given prompt using Ollama API."""
        response = ollama.chat(model=model_name, messages=[{'role': 'user', 'content': prompt}])
        return response['message']['content'].strip()

    def is_valid_json(self):
        ''' check if the file is valid json
		'''

        try:
            json.loads(open(self.f_name).read())
        except ValueError as e:			
            return False

        return True
    def is_valid_json_aif(sel,aif_nodes):
        if 'nodes' in aif_nodes and 'locutions' in aif_nodes and 'edges' in aif_nodes:
            return True
        return False

    def get_aif(self, format='xAIF'):
        if self.is_valid_json():
            with open(self.f_name) as file:
                data = file.read()
                x_aif = json.loads(data)
                if format == "xAIF":
                    return x_aif
                else:
                    aif = x_aif.get('AIF')
                    return json.dumps(aif)
        else:
            return "Invalid json"



    def extract_relation(self, response):
        # Remove <think> tags and their content
        response_cleaned = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL)
        logging.info(f"response_cleaned: {response_cleaned}")

        relation = "None"  # Default value

        try:
            # Extract JSON substring from response if present
            json_match = re.search(r'\{.*?\}', response_cleaned, re.DOTALL)
            if json_match:
                parsed_response = json.loads(json_match.group())

                if isinstance(parsed_response, dict):
                    # Handle dictionary formats: {'relation': label} and {relation: label}
                    if "relation" in parsed_response:
                        relation = parsed_response["relation"]
                    elif parsed_response:
                        relation = list(parsed_response.values())[0]  # Return the first value
            else:
                # If no JSON, check for "relation:label" format
                match = re.search(r'relation\s*:\s*(\w+)', response_cleaned, re.IGNORECASE)
                if match:
                    relation = match.group(1).strip()

        except (ValueError, json.JSONDecodeError):
            pass  # If JSON parsing fails, continue alternative extraction
                # Handle "relation:label" format
        if '"relation":' in response_cleaned:
            relation = response_cleaned.split(":", 1)[1].strip()

        return relation


    def extract_relation__(self, response):
        # Remove <think> tags and their content
        response_cleaned = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL)
        logging.info(f"response_cleaned ============================:  {response_cleaned}, {response_cleaned}") 

        try:
            # Try parsing as JSON
            parsed_response = json.loads(response_cleaned)

            if isinstance(parsed_response, dict):
                # Handle dictionary formats: {'relation': label} and {relation: label}
                if "relation" in parsed_response:
                    return parsed_response["relation"]
                elif parsed_response:
                    return list(parsed_response.values())[0]  # Return the first value
            elif isinstance(parsed_response, str):
                if ":" in response_cleaned:
                    return response_cleaned.split(":", 1)[1].strip()

        except ValueError:
            pass  # Not JSON, try alternative parsing

        # Handle "relation:label" format
        if ":" in response_cleaned:
            return response_cleaned.split(":", 1)[1].strip()

        return "None"


    def get_argument_structure(self):
        """Retrieve the argument structure from the input data."""
        data = self.get_aif()
        if not data:
            return "Invalid input"
        
        x_aif = self.aif_obj.xaif
        aif =  self.aif_obj.aif
        if not self.is_valid_aif(aif):
            return "Invalid json-aif"

        propositions_id_pairs = self.get_propositions_id_pairs(aif)
        self.update_node_edge_with_relations(propositions_id_pairs)

        return x_aif


    def is_valid_aif(self, aif):
        """Check if the AIF data is valid."""
        return 'nodes' in aif and 'edges' in aif

    def get_propositions_id_pairs(self, aif):
        """Extract proposition ID pairs from the AIF data."""
        propositions_id_pairs = {}
        for node in aif.get('nodes', []):
            if node.get('type') == "I":
                proposition = node.get('text', '').strip()
                if proposition:
                    node_id = node.get('nodeID')
                    propositions_id_pairs[node_id] = proposition
        return propositions_id_pairs
    
    def update_node_edge_with_relations(self, propositions_id_pairs):
        """
        Update the nodes and edges in the AIF structure to reflect the new relations between propositions.
        """
        checked_pairs = set()
        for prop1_node_id, prop1 in propositions_id_pairs.items():
            for prop2_node_id, prop2 in propositions_id_pairs.items():
                if prop1_node_id != prop2_node_id:
                    pair1 = (prop1_node_id, prop2_node_id)
                    pair2 = (prop2_node_id, prop1_node_id)
                    if pair1 not in checked_pairs and pair2 not in checked_pairs:
                        checked_pairs.add(pair1)
                        checked_pairs.add(pair2)
                        prompt = f"""
                            Given the two argumentative texts:
                            1. {prop1}
                            2. {prop2}
                            
                            Classify their argument relationship as one of the following: 'Support' if one is support the other, 'Attack' if one attacks the other, 'Rephrase' if one rephrase the other, or 'None' if no argument relation exists.
                            Do not rephrase, or summarise, the existing text as it is. Do not also add any text other than what is provided.
                            Do not include explanations or thinking steps. 
                    
                            Provide the classification as a JSON object in the format: relation: relation_type.
                            """
                        
                        response = self.llm_model(prompt)
                        
                        relation = self.extract_relation(response)
                      
                        logging.info(f"Relation is ============================:  {relation}") 

                        if relation in ['Support', 'support']:
                            predictions = "RA"
                        elif relation in ['Attack','attack']:
                            predictions = "CA"
                        elif relation in ['Rephrase','rephrase']:
                            predictions = "MA"
                        else:
                            predictions = "None"

                        #for prediction in predictions:
                        if predictions in ['RA','MA','CA']:
                            self.aif_obj.add_component("argument_relation", predictions, prop1_node_id, prop2_node_id)
                            



    def update_node_edge_with_relations__(self, propositions_id_pairs, batch_size=4):
        """
        Update the nodes and edges in the AIF structure to reflect the new relations between propositions.
        """
        pairs_to_predict = []
        pair_ids = []

        # Use combinations to create pairs without redundant checking
        for (prop1_node_id, prop1), (prop2_node_id, prop2) in combinations(propositions_id_pairs.items(), 2):
            pairs_to_predict.append(prop1+ "" + prop2)
            pair_ids.append((prop1_node_id, prop2_node_id))

        # Process pairs in batches
        for i in range(0, len(pairs_to_predict), batch_size):
            batch_pairs = pairs_to_predict[i:i+batch_size]
            batch_pair_ids = pair_ids[i:i+batch_size]
            
            # Assuming `self.model.predict` can handle batches of inputs
            #predictions = self.model.predict(batch_pairs)
            predictions = self.llm_model(batch_pairs)
            
            for (prop1_node_id, prop2_node_id), prediction in zip(batch_pair_ids, predictions):
                if prediction in ['RA', 'MA', 'CA']:
                    self.aif_obj.add_component("argument_relation", prediction, prop1_node_id, prop2_node_id)
                    
