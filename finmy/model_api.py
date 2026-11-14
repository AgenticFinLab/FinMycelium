"""FinMycelium model transport, extending the existing lmbase API interface."""
import os
import time

from lmbase.inference.api_call import LangChainAPIInference

from finmy.model_config import api_key_variable, generation_parameters, model_name, tokenhub_base_url


class ModelAPIInference(LangChainAPIInference):
    """Keep lmbase behavior for existing providers; add TokenHub Chat Completions."""

    def __init__(self, lm_name=None, generation_config=None):
        lm_name = model_name(lm_name)
        use_default_limit = not generation_config
        generation_config = generation_parameters(lm_name, generation_config)
        provider, identifier = lm_name.split('/', 1)
        if provider != 'tokenhub':
            super().__init__(lm_name=lm_name, generation_config=generation_config)
        else:
            from lmbase.inference.base import BaseLMAPIInference
            BaseLMAPIInference.__init__(self, lm_name=lm_name, generation_config=generation_config)
            self.lm_provider = provider
            self.model_name = identifier
            self.base_url = tokenhub_base_url()
            variable = api_key_variable(provider)
            self.api_key = os.environ.get(variable)
            if not self.api_key:
                raise ValueError('Set ' + variable + ' for TokenHub model calls')
            self.max_tokens = 8192
            # Reuse message conversion, response accounting and the OpenAI SDK.
            # Search and bounded Builders disable SDK retries in their adapters.
            self._initialize_client()
        if use_default_limit or not self.generation_config:
            # Sampling defaults make the config nonempty. Preserve lmbase's
            # 8192-token fallback instead of accidentally using the service cap.
            self.generation_config = generation_parameters(
                lm_name, {'max_tokens': self.max_tokens})

    def request_parameters(self, parameters):
        return generation_parameters(self.lm_name, parameters)

    def run(self, infer_inputs=None, *, infer_input=None, **kwargs):
        """Support Agent's single-input call and lmbase's current batch API."""
        if infer_inputs is not None:
            if infer_input is not None:
                raise ValueError('Use infer_input or infer_inputs, not both')
            return super().run(infer_inputs, **kwargs)
        if infer_input is None:
            raise ValueError('An inference input is required')
        started = time.perf_counter()
        messages = (infer_input.messages if infer_input.messages is not None
                    else self._create_messages(infer_input, **kwargs))
        output = self._inference(messages)
        output.cost.time_used = time.perf_counter() - started
        return output
