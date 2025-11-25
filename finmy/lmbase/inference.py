"""
LLM service of AIHUBMIX


Model List: https://aihubmix.com/models
Documentation: https://docs.aihubmix.com/cn

"""

import os
import random
from openai import OpenAI
from dotenv import load_dotenv


def api_call(prompt: str, model_id: str) -> str:

    load_dotenv()
    AIHUBMIX_API_KEY = os.getenv("AIHUBMIX_API_KEY")
    AIHUBMIX_BASE_URL = os.getenv("AIHUBMIX_BASE_URL")

    client = OpenAI(
        base_url=AIHUBMIX_BASE_URL,
        api_key=AIHUBMIX_API_KEY,
    )

    completion = client.chat.completions.create(
        model=model_id,  # model ID, copy from https://aihubmix.com/models
        messages=[
            # {"role": "developer", "content": ""},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        max_tokens=1024,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0,
        seed=random.randint(1, 1000000000),
    )

    return completion.choices[0].message.content


if __name__ == "__main__":
    print(api_call(prompt="蓝天格锐庞氏骗局", model_id="qwen-plus-latest"))
