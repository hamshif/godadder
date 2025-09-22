import uvicorn
import requests
import json
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, ValidationError, Field
from typing import Type, TypeVar, List
from godadder import nameriffer

# --- 1. Pydantic Models ---
# Model for the structured AI output
class User(BaseModel):
    name: str
    age: int

# Model for the incoming request body
class PromptRequest(BaseModel):
    text: str

# A Generic Type for our Agent's output model
T = TypeVar('T', bound=BaseModel)


# --- 2. Our Custom Ollama Agent ---
# This class encapsulates the logic for calling Ollama and validating the response.
class OllamaAgent:
    def __init__(self, output_model: Type[T], model_name: str = "llama3"):
        self.output_model = output_model
        self.model_name = model_name
        self.ollama_url = "http://localhost:11434/api/generate"

    def run(self, prompt: str) -> T:
        """
        Runs the agent: sends a prompt to Ollama, gets a response,
        and validates it against the specified Pydantic model.
        """
        # CORRECTED: We now generate the JSON schema from the Pydantic model
        # and include it directly in the prompt.
        schema = self.output_model.model_json_schema()
        
        json_prompt = f"""
        Please extract the information from the following text and provide it as a single, valid JSON object that strictly adheres to the following JSON Schema.
        Do not include any other text, explanations, or markdown backticks.

        Text: "{prompt}"
        
        JSON Schema:
        {json.dumps(schema, indent=2)}

        JSON Output:
        """
        body = {
            "model": self.model_name,
            "prompt": json_prompt,
            "stream": False,
            "format": "json" # Add format parameter to ensure JSON output
        }
        
        try:
            # Call the Ollama API
            response = requests.post(self.ollama_url, json=body, timeout=60)
            response.raise_for_status()
            data = response.json()
            response_text = data.get("response", "{}")
            # The response from Ollama with format=json is already a JSON object string
            raw_data = json.loads(response_text)
            
            # Validate the response with the Pydantic model
            validated_output = self.output_model(**raw_data)
            return validated_output
            
        except requests.exceptions.RequestException as e:
            print(f"Error calling Ollama API: {e}")
            raise HTTPException(status_code=502, detail="Error communicating with the Ollama service.")
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON from Ollama response: {e}")
            print(f"Received text: {response_text}")
            raise HTTPException(status_code=500, detail="The AI model returned invalid JSON.")
        except ValidationError as e:
            print(f"Pydantic validation failed: {e}")
            raise HTTPException(status_code=500, detail="AI model output did not match the required structure.")


# --- 3. FastAPI Application Setup ---
app = FastAPI(
    title="Structured Data Extractor (Agent Architecture)",
    description="Uses a custom agent to manage Ollama interaction.",
    version="2.1.0",
)

# Create a single, reusable instance of our agent
user_agent = OllamaAgent(output_model=User)


# --- 4. API Endpoint ---
# The endpoint is now much cleaner, as the logic is in the agent.
@app.post("/extract-user", response_model=User)
def extract_user_data(request: PromptRequest):
    """
    Receives text, uses the agent to extract and validate user data, and returns it.
    """
    print(f"Received request with text: '{request.text}'")
    try:
        validated_user = user_agent.run(request.text)
        print(f"Successfully validated data: {validated_user}")
        return validated_user
    except HTTPException as e:
        # Re-raise the exception if the agent threw one
        raise e
    except Exception as e:
        # Catch any other unexpected errors
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")


# --- 4b. Riff Startup Names Endpoint ---
class RiffRequest(BaseModel):
    base: str
    count: int = Field(ge=1, le=50)


class NamesResponse(BaseModel):
    names: List[str]


# --- 4c. Name Riffing Agent (DI) ---
class NameRiffAgent:
    def riff(self, base: str, count: int) -> List[str]:
        raise NotImplementedError


class DefaultNameRiffAgent(NameRiffAgent):
    def __init__(self, model: str = "llama3.3:latest"):
        self.model = model

    def riff(self, base: str, count: int) -> List[str]:
        return nameriffer.ollama_riff(self.model, base, n=count)


_default_riff_agent: NameRiffAgent = DefaultNameRiffAgent()


def get_riff_agent() -> NameRiffAgent:
    return _default_riff_agent


@app.post("/riff-names", response_model=NamesResponse)
def riff_names(request: RiffRequest, agent: NameRiffAgent = Depends(get_riff_agent)):
    try:
        names = agent.riff(request.base, request.count)
        return NamesResponse(names=names)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Riff error: {e}")

# --- 5. Server Runner ---
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
