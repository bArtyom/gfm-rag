# Amendment 003: scorer tokenizer warning

- Date: 2026-11-23.
- The local Jina checkpoint declares the tokenizer class `XLMRobertaTokenizer`, but its older `config.json` lacks `model_type` while retaining `transformers_version=4.40.0`. Transformers 4.57.6 therefore emitted a Mistral-regex warning while loading this XLM-R tokenizer. The recommended `fix_mistral_regex=True` would replace the tokenizer's pre-tokenizer with a Mistral pattern, which is not appropriate for XLM-R.
- Set `fix_mistral_regex=false` explicitly and assert the loaded tokenizer class is from the XLMRoberta family. This preserves the model's local tokenizer behavior and suppresses the false-positive Mistral patch warning. Record the loaded class and setting in each private scorer manifest.
- This is a tokenizer-loading clarification only. It does not change candidate text, score transform, acquisition, budgets, stop rules, or the cached Qwen vectors.
