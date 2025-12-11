from finmy.builder.lm_build_flow import lm_build_flow_main, get_sample_raw_texts
from datetime import datetime


if __name__ == "__main__":
    raw_texts = get_sample_raw_texts()
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    lm_build_flow_main(raw_texts=raw_texts, query_text="识别与人工智能在金融风控与合规相关的内容", key_words=["人工智能", "AI", "风险管理", "模型合规", "透明度"],output_dir=f"./examples/utest/Collector/test_files/event_output_{timestamp}")
