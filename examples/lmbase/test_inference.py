"""
Test for LLM service of AIHUBMIX


Model List: https://aihubmix.com/models
Documentation: https://docs.aihubmix.com/cn

"""

from finmy.lmbase.inference import api_call


if __name__ == "__main__":

    # model_id: can be copied from https://aihubmix.com/models   (Copy ID)
    print(api_call(prompt="蓝天格锐庞氏骗局", model_id="qwen-plus-latest"))
