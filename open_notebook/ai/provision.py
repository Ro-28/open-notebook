from esperanto import LanguageModel
from langchain_core.language_models.chat_models import BaseChatModel
from loguru import logger

from open_notebook.ai.models import model_manager
from open_notebook.exceptions import ConfigurationError
from open_notebook.utils import token_count


async def provision_langchain_model(
    content, model_id, default_type, **kwargs
) -> BaseChatModel:
    """
    Returns the best model to use based on the context size and on whether there is a specific model being requested in Config.
    If context > 105_000, returns the large_context_model
    If model_id is specified in Config, returns that model
    Otherwise, returns the default model for the given type
    """
    tokens = token_count(content)
    model = None
    selection_reason = ""

    # Fork: the large-context switch honours the chosen model's own context window when it
    # is known (Settings > Models), instead of a fixed 105k threshold. Leave ~15% headroom.
    threshold = 105_000
    try:
        from open_notebook.ai.models import Model
        from open_notebook.ai.models import model_manager as _mm

        chosen_id = model_id
        if not chosen_id:
            defaults = await _mm.get_defaults()
            chosen_id = {
                "chat": defaults.default_chat_model,
                "transformation": defaults.default_transformation_model or defaults.default_chat_model,
                "tools": defaults.default_tools_model or defaults.default_chat_model,
            }.get(default_type)
        if chosen_id:
            chosen = await Model.get(chosen_id)
            if chosen and chosen.context_window:
                threshold = int(chosen.context_window * 0.85)
    except Exception as e:  # noqa: BLE001 - never block provisioning on the lookup
        logger.debug(f"context_window lookup skipped: {e}")

    if tokens > threshold:
        selection_reason = f"large_context (content has {tokens} tokens > {threshold})"
        logger.debug(
            f"Using large context model because the content has {tokens} tokens"
        )
        model = await model_manager.get_default_model("large_context", **kwargs)
    elif model_id:
        selection_reason = f"explicit model_id={model_id}"
        model = await model_manager.get_model(model_id, **kwargs)
    else:
        selection_reason = f"default for type={default_type}"
        model = await model_manager.get_default_model(default_type, **kwargs)

    logger.debug(f"Using model: {model}")

    if model is None:
        logger.error(
            f"Model provisioning failed: No model found. "
            f"Selection reason: {selection_reason}. "
            f"model_id={model_id}, default_type={default_type}. "
            f"Please check Manage → Models and ensure a default model is configured for '{default_type}'."
        )
        raise ConfigurationError(
            f"No model configured for {selection_reason}. "
            f"Please go to Manage → Models and configure a default model for '{default_type}'."
        )

    if not isinstance(model, LanguageModel):
        logger.error(
            f"Model type mismatch: Expected LanguageModel but got {type(model).__name__}. "
            f"Selection reason: {selection_reason}. "
            f"model_id={model_id}, default_type={default_type}."
        )
        raise ConfigurationError(
            f"Model is not a LanguageModel: {model}. "
            f"Please check that the model configured for '{default_type}' is a language model, not an embedding or speech model."
        )

    return model.to_langchain()
