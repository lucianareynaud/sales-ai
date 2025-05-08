import os
import json
import re
from typing import Dict, Any

from openai import AsyncOpenAI
from shared.db import get_transcript_by_id

# Load the extraction prompt (in Brazilian Portuguese)
prompt_path = os.path.join(
    os.path.dirname(__file__),
    "prompts",
    "extract_sales_pt.txt"
)
with open(prompt_path, encoding="utf-8") as f:
    EXTRACT_PROMPT = f.read()

# Configure model and API Key
env_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def extract_sales_data_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    LangGraph Node: reads transcript, sends prompt to LLM and returns structured JSON.
    
    Args:
        state: A dictionary containing:
            - state["transcript_id"]: Meeting ID in Postgres
    
    Returns:
        The updated state dict with:
            - state["sales_data"]: The extracted sales intelligence data, with keys:
                "empresa", "stakeholders", "dores", "oportunidades", "gatilhos_pesquisa", "contexto_personalizacao", "solucoes", "marcas", "spin", "bant"
    
    Raises:
        ValueError: If JSON parsing fails
    """
    # 1. Get transcript and language
    transcript_id = state.get("transcript_id")
    transcript_text, language = get_transcript_by_id(transcript_id)

    # 2. Call the LLM for extraction
    response = await client.chat.completions.create(
        model=env_model,
        messages=[
            {"role": "system", "content": EXTRACT_PROMPT},
            {"role": "user", "content": transcript_text}
        ],
        temperature=0.0
    )
    raw = response.choices[0].message.content

    print("Raw response from LLM:", raw)

    # 3. Parse JSON, with fallback to extract JSON block
    try:
        sales_data = json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract JSON block from text response
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                sales_data = json.loads(match.group(0))
            except json.JSONDecodeError:
                raise ValueError(f"Could not parse JSON from LLM response: {raw}")
        else:
            raise ValueError(f"Could not parse JSON from LLM response: {raw}")

    # Ensure SPIN and BANT are present with correct structure
    # Primeiro, salva o estado original do JSON (para debugging)
    original_json = json.dumps(sales_data, indent=2, ensure_ascii=False)
    print("Original JSON antes das transformações:", original_json)
    
    try:
        # FORÇAR campos SPIN e BANT como estruturas concretas
        # Independentemente do que a LLM retornar, teremos a estrutura correta
        
        # Criar estrutura definitiva para SPIN
        spin_data = {
            "situacao": "Situação não identificada na transcrição",
            "problema": "Problemas não identificados na transcrição",
            "implicacao": "Implicações não identificadas na transcrição",
            "necessidade": "Necessidades não identificadas na transcrição"
        }
        
        # Se o LLM tentar retornar dados de SPIN, tentamos extraí-los
        if "spin" in sales_data:
            # Caso o modelo retorne um objeto estruturado
            if isinstance(sales_data["spin"], dict):
                if "situacao" in sales_data["spin"] and sales_data["spin"]["situacao"]:
                    spin_data["situacao"] = str(sales_data["spin"]["situacao"])
                if "problema" in sales_data["spin"] and sales_data["spin"]["problema"]:
                    spin_data["problema"] = str(sales_data["spin"]["problema"])
                if "implicacao" in sales_data["spin"] and sales_data["spin"]["implicacao"]:
                    spin_data["implicacao"] = str(sales_data["spin"]["implicacao"])
                if "necessidade" in sales_data["spin"] and sales_data["spin"]["necessidade"]:
                    spin_data["necessidade"] = str(sales_data["spin"]["necessidade"])
            # Caso o modelo retorne uma string
            elif isinstance(sales_data["spin"], str) and len(sales_data["spin"]) > 5:
                spin_data["situacao"] = str(sales_data["spin"])
        
        # Criar estrutura definitiva para BANT
        bant_data = {
            "budget": "Orçamento não identificado na transcrição",
            "authority": "Autoridades não identificadas na transcrição",
            "need": "Necessidades não identificadas na transcrição",
            "timeline": "Prazos não identificados na transcrição"
        }
        
        # Se o LLM tentar retornar dados de BANT, tentamos extraí-los
        if "bant" in sales_data:
            # Caso o modelo retorne um objeto estruturado
            if isinstance(sales_data["bant"], dict):
                if "budget" in sales_data["bant"] and sales_data["bant"]["budget"]:
                    bant_data["budget"] = str(sales_data["bant"]["budget"])
                if "authority" in sales_data["bant"] and sales_data["bant"]["authority"]:
                    bant_data["authority"] = str(sales_data["bant"]["authority"])
                if "need" in sales_data["bant"] and sales_data["bant"]["need"]:
                    bant_data["need"] = str(sales_data["bant"]["need"])
                if "timeline" in sales_data["bant"] and sales_data["bant"]["timeline"]:
                    bant_data["timeline"] = str(sales_data["bant"]["timeline"])
            # Caso o modelo retorne uma string
            elif isinstance(sales_data["bant"], str) and len(sales_data["bant"]) > 5:
                bant_data["budget"] = str(sales_data["bant"])
        
        # Substituir as estruturas no objeto de saída
        sales_data["spin"] = spin_data
        sales_data["bant"] = bant_data
        
        # Criar chaves no formato consistente
        # Garantir que os campos existam com os nomes exatos esperados
        for key in ["empresa", "stakeholders", "dores", "oportunidades", 
                   "gatilhos_pesquisa", "contexto_personalizacao", "solucoes", "marcas"]:
            if key not in sales_data:
                sales_data[key] = None
            
            # Se o campo deveria ser uma lista mas não é
            if key in ["stakeholders", "dores", "oportunidades", "gatilhos_pesquisa", "solucoes", "marcas"]:
                if not isinstance(sales_data[key], list) and sales_data[key] is not None:
                    try:
                        # Tenta converter para lista se for string
                        if isinstance(sales_data[key], str):
                            sales_data[key] = [sales_data[key]]
                        else:
                            sales_data[key] = []
                    except:
                        sales_data[key] = []
        
        # Log do JSON processado para diagnóstico
        processed_json = json.dumps(sales_data, indent=2, ensure_ascii=False)
        print("JSON após processamento:", processed_json)
    
    except Exception as e:
        print(f"Erro ao processar campos SPIN/BANT: {e}")

    # Log the final structure
    print("Final sales_data structure:", json.dumps(sales_data, indent=2, ensure_ascii=False))
        
    # 4. Store in state for subsequent nodes
    state["sales_data"] = sales_data
    return state 