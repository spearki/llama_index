"""Test recursive queries."""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict, List, Tuple, cast
from unittest.mock import patch

import pytest

from gpt_index.data_structs.data_structs_v2 import V2IndexStruct
from gpt_index.data_structs.struct_type import IndexStructType
from gpt_index.embeddings.openai import OpenAIEmbedding
from gpt_index.indices.composability.graph import ComposableGraph
from gpt_index.indices.keyword_table.simple_base import GPTSimpleKeywordTableIndex
from gpt_index.indices.list.base import GPTListIndex
from gpt_index.indices.query.schema import QueryConfig, QueryMode
from gpt_index.indices.tree.base import GPTTreeIndex
from gpt_index.indices.vector_store.vector_indices import GPTSimpleVectorIndex
from gpt_index.langchain_helpers.chain_wrapper import (
    LLMChain,
    LLMMetadata,
    LLMPredictor,
)
from gpt_index.langchain_helpers.text_splitter import TokenTextSplitter
from gpt_index.readers.schema.base import Document
from tests.mock_utils.mock_predict import (
    mock_llmchain_predict,
    mock_llmpredictor_predict,
)
from tests.mock_utils.mock_prompts import (
    MOCK_INSERT_PROMPT,
    MOCK_KEYWORD_EXTRACT_PROMPT,
    MOCK_QUERY_KEYWORD_EXTRACT_PROMPT,
    MOCK_QUERY_PROMPT,
    MOCK_REFINE_PROMPT,
    MOCK_SUMMARY_PROMPT,
    MOCK_TEXT_QA_PROMPT,
)
from tests.mock_utils.mock_text_splitter import mock_token_splitter_newline


@pytest.fixture
def struct_kwargs() -> Tuple[Dict, List]:
    """Index kwargs."""
    index_kwargs = {
        "tree": {
            "summary_template": MOCK_SUMMARY_PROMPT,
            "insert_prompt": MOCK_INSERT_PROMPT,
            "num_children": 2,
        },
        "list": {
            "text_qa_template": MOCK_TEXT_QA_PROMPT,
        },
        "table": {
            "keyword_extract_template": MOCK_KEYWORD_EXTRACT_PROMPT,
        },
        "vector": {},
    }
    query_configs = [
        QueryConfig(
            index_struct_type=IndexStructType.TREE,
            query_mode=QueryMode.DEFAULT,
            query_kwargs={
                "query_template": MOCK_QUERY_PROMPT,
                "text_qa_template": MOCK_TEXT_QA_PROMPT,
                "refine_template": MOCK_REFINE_PROMPT,
            },
        ),
        QueryConfig(
            index_struct_type=IndexStructType.LIST,
            query_mode=QueryMode.DEFAULT,
            query_kwargs={
                "text_qa_template": MOCK_TEXT_QA_PROMPT,
                "refine_template": MOCK_REFINE_PROMPT,
            },
        ),
        QueryConfig(
            index_struct_type=IndexStructType.KEYWORD_TABLE,
            query_mode=QueryMode.DEFAULT,
            query_kwargs={
                "query_keyword_extract_template": MOCK_QUERY_KEYWORD_EXTRACT_PROMPT,
                "text_qa_template": MOCK_TEXT_QA_PROMPT,
                "refine_template": MOCK_REFINE_PROMPT,
            },
        ),
        QueryConfig(
            index_struct_type=IndexStructType.DICT,
            query_mode=QueryMode.DEFAULT,
            query_kwargs={
                "text_qa_template": MOCK_TEXT_QA_PROMPT,
                "refine_template": MOCK_REFINE_PROMPT,
                "similarity_top_k": 1,
            },
        ),
    ]
    return index_kwargs, query_configs


@pytest.fixture
def documents() -> List[Document]:
    """Get documents."""
    docs = [
        Document("This is a test v2."),
        Document("This is another test."),
        Document("This is a test."),
        Document("Hello world."),
        Document("Hello world."),
        Document("This is a test."),
        Document("This is another test."),
        Document("This is a test v2."),
    ]
    return docs


@patch.object(TokenTextSplitter, "split_text", side_effect=mock_token_splitter_newline)
@patch.object(LLMPredictor, "predict", side_effect=mock_llmpredictor_predict)
@patch.object(LLMPredictor, "total_tokens_used", return_value=0)
@patch.object(LLMPredictor, "__init__", return_value=None)
def test_recursive_query_list_tree(
    _mock_init: Any,
    _mock_total_tokens_used: Any,
    _mock_predict: Any,
    _mock_split_text: Any,
    documents: List[Document],
    struct_kwargs: Dict,
) -> None:
    """Test query."""
    index_kwargs, query_configs = struct_kwargs
    list_kwargs = index_kwargs["list"]
    tree_kwargs = index_kwargs["tree"]
    # try building a list for every two, then a tree
    list1 = GPTListIndex.from_documents(documents[0:2], **list_kwargs)
    list2 = GPTListIndex.from_documents(documents[2:4], **list_kwargs)
    list3 = GPTListIndex.from_documents(documents[4:6], **list_kwargs)
    list4 = GPTListIndex.from_documents(documents[6:8], **list_kwargs)

    summary1 = "summary1"
    summary2 = "summary2"
    summary3 = "summary3"
    summary4 = "summary4"
    summaries = [summary1, summary2, summary3, summary4]

    # there are two root nodes in this tree: one containing [list1, list2]
    # and the other containing [list3, list4]
    graph = ComposableGraph.from_indices(
        GPTTreeIndex,
        [
            list1,
            list2,
            list3,
            list4,
        ],
        index_summaries=summaries,
        **tree_kwargs
    )
    assert isinstance(graph, ComposableGraph)
    query_str = "What is?"
    # query should first pick the left root node, then pick list1
    # within list1, it should go through the first document and second document
    response = graph.query(query_str, query_configs=query_configs)
    assert str(response) == ("What is?:What is?:This is a test v2.")


@patch.object(TokenTextSplitter, "split_text", side_effect=mock_token_splitter_newline)
@patch.object(LLMPredictor, "predict", side_effect=mock_llmpredictor_predict)
@patch.object(LLMPredictor, "total_tokens_used", return_value=0)
@patch.object(LLMPredictor, "__init__", return_value=None)
def test_recursive_query_tree_list(
    _mock_init: Any,
    _mock_total_tokens_used: Any,
    _mock_predict: Any,
    _mock_split_text: Any,
    documents: List[Document],
    struct_kwargs: Dict,
) -> None:
    """Test query."""
    index_kwargs, query_configs = struct_kwargs
    list_kwargs = index_kwargs["list"]
    tree_kwargs = index_kwargs["tree"]
    # try building a tree for a group of 4, then a list
    # use a diff set of documents
    tree1 = GPTTreeIndex.from_documents(documents[2:6], **tree_kwargs)
    tree2 = GPTTreeIndex.from_documents(documents[:2] + documents[6:], **tree_kwargs)
    summaries = [
        "tree_summary1",
        "tree_summary2",
    ]

    # there are two root nodes in this tree: one containing [list1, list2]
    # and the other containing [list3, list4]
    graph = ComposableGraph.from_indices(
        GPTListIndex, [tree1, tree2], index_summaries=summaries, **list_kwargs
    )
    assert isinstance(graph, ComposableGraph)
    query_str = "What is?"
    # query should first pick the left root node, then pick list1
    # within list1, it should go through the first document and second document
    response = graph.query(query_str, query_configs=query_configs)
    assert str(response) == ("What is?:What is?:This is a test.")


@patch.object(TokenTextSplitter, "split_text", side_effect=mock_token_splitter_newline)
@patch.object(LLMPredictor, "predict", side_effect=mock_llmpredictor_predict)
@patch.object(LLMPredictor, "total_tokens_used", return_value=0)
@patch.object(LLMPredictor, "__init__", return_value=None)
def test_recursive_query_table_list(
    _mock_init: Any,
    _mock_total_tokens_used: Any,
    _mock_predict: Any,
    _mock_split_text: Any,
    documents: List[Document],
    struct_kwargs: Dict,
) -> None:
    """Test query."""
    index_kwargs, query_configs = struct_kwargs
    list_kwargs = index_kwargs["list"]
    table_kwargs = index_kwargs["table"]
    # try building a tree for a group of 4, then a list
    # use a diff set of documents
    table1 = GPTSimpleKeywordTableIndex.from_documents(documents[4:6], **table_kwargs)
    table2 = GPTSimpleKeywordTableIndex.from_documents(documents[2:3], **table_kwargs)
    summaries = [
        "table_summary1",
        "table_summary2",
    ]

    graph = ComposableGraph.from_indices(
        GPTListIndex, [table1, table2], index_summaries=summaries, **list_kwargs
    )
    assert isinstance(graph, ComposableGraph)
    query_str = "World?"
    response = graph.query(query_str, query_configs=query_configs)
    assert str(response) == ("World?:World?:Hello world.")

    query_str = "Test?"
    response = graph.query(query_str, query_configs=query_configs)
    assert str(response) == ("Test?:Test?:This is a test.")

    # test serialize and then back
    with TemporaryDirectory() as tmpdir:
        graph.save_to_disk(str(Path(tmpdir) / "tmp.json"))
        graph = ComposableGraph.load_from_disk(str(Path(tmpdir) / "tmp.json"))
        response = graph.query(query_str, query_configs=query_configs)
        assert str(response) == ("Test?:Test?:This is a test.")


@patch.object(TokenTextSplitter, "split_text", side_effect=mock_token_splitter_newline)
@patch.object(LLMPredictor, "predict", side_effect=mock_llmpredictor_predict)
@patch.object(LLMPredictor, "total_tokens_used", return_value=0)
@patch.object(LLMPredictor, "__init__", return_value=None)
def test_recursive_query_list_table(
    _mock_init: Any,
    _mock_total_tokens_used: Any,
    _mock_predict: Any,
    _mock_split_text: Any,
    documents: List[Document],
    struct_kwargs: Dict,
) -> None:
    """Test query."""
    index_kwargs, query_configs = struct_kwargs
    list_kwargs = index_kwargs["list"]
    table_kwargs = index_kwargs["table"]
    # try building a tree for a group of 4, then a list
    # use a diff set of documents
    # try building a list for every two, then a tree
    list1 = GPTListIndex.from_documents(documents[0:2], **list_kwargs)
    list2 = GPTListIndex.from_documents(documents[2:4], **list_kwargs)
    list3 = GPTListIndex.from_documents(documents[4:6], **list_kwargs)
    list4 = GPTListIndex.from_documents(documents[6:8], **list_kwargs)
    summaries = [
        "foo bar",
        "apple orange",
        "toronto london",
        "cat dog",
    ]

    graph = ComposableGraph.from_indices(
        GPTSimpleKeywordTableIndex,
        [list1, list2, list3, list4],
        index_summaries=summaries,
        **table_kwargs
    )
    assert isinstance(graph, ComposableGraph)
    query_str = "Foo?"
    response = graph.query(query_str, query_configs=query_configs)
    assert str(response) == ("Foo?:Foo?:This is a test v2.")
    query_str = "Orange?"
    response = graph.query(query_str, query_configs=query_configs)
    assert str(response) == ("Orange?:Orange?:This is a test.")
    query_str = "Cat?"
    response = graph.query(query_str, query_configs=query_configs)
    assert str(response) == ("Cat?:Cat?:This is another test.")

    # test serialize and then back
    # use composable graph struct
    with TemporaryDirectory() as tmpdir:
        graph.save_to_disk(str(Path(tmpdir) / "tmp.json"))
        graph = ComposableGraph.load_from_disk(str(Path(tmpdir) / "tmp.json"))
        response = graph.query(query_str, query_configs=query_configs)
        assert str(response) == ("Cat?:Cat?:This is another test.")


@patch.object(LLMChain, "predict", side_effect=mock_llmchain_predict)
@patch("gpt_index.llm_predictor.base.OpenAI")
@patch.object(LLMPredictor, "get_llm_metadata", return_value=LLMMetadata())
@patch.object(LLMChain, "__init__", return_value=None)
def test_recursive_query_list_tree_token_count(
    _mock_init: Any,
    _mock_llm_metadata: Any,
    _mock_llmchain: Any,
    _mock_predict: Any,
    documents: List[Document],
    struct_kwargs: Dict,
) -> None:
    """Test query."""
    index_kwargs, query_configs = struct_kwargs
    list_kwargs = index_kwargs["list"]
    tree_kwargs = index_kwargs["tree"]
    # try building a list for every two, then a tree
    list1 = GPTListIndex.from_documents(documents[0:2], **list_kwargs)
    list2 = GPTListIndex.from_documents(documents[2:4], **list_kwargs)
    list3 = GPTListIndex.from_documents(documents[4:6], **list_kwargs)
    list4 = GPTListIndex.from_documents(documents[6:8], **list_kwargs)

    summary1 = "summary1"
    summary2 = "summary2"
    summary3 = "summary3"
    summary4 = "summary4"
    summaries = [summary1, summary2, summary3, summary4]

    # there are two root nodes in this tree: one containing [list1, list2]
    # and the other containing [list3, list4]
    # import pdb; pdb.set_trace()
    graph = ComposableGraph.from_indices(
        GPTTreeIndex,
        [
            list1,
            list2,
            list3,
            list4,
        ],
        index_summaries=summaries,
        **tree_kwargs
    )
    assert isinstance(graph, ComposableGraph)
    # first pass prompt is "summary1\nsummary2\n" (6 tokens),
    # response is the mock response (10 tokens)
    # total is 16 tokens, multiply by 2 to get the total
    assert graph.service_context.llm_predictor.total_tokens_used == 32

    query_str = "What is?"
    # query should first pick the left root node, then pick list1
    # within list1, it should go through the first document and second document
    start_token_ct = graph.service_context.llm_predictor.total_tokens_used
    graph.query(query_str, query_configs=query_configs)
    # prompt is which is 35 tokens, plus 10 for the mock response
    assert graph.service_context.llm_predictor.total_tokens_used - start_token_ct == 45


def mock_get_query_embedding(query: str) -> List[float]:
    """Mock get query embedding."""
    if query == "Foo?":
        return [0, 0, 1, 0, 0]
    elif query == "Orange?":
        return [0, 1, 0, 0, 0]
    elif query == "Cat?":
        return [0, 0, 0, 1, 0]
    else:
        raise ValueError("Invalid query for `mock_get_query_embedding`.")


def mock_get_text_embedding(text: str) -> List[float]:
    """Mock get text embedding."""
    # assume dimensions are 5
    if text == "Hello world.":
        return [1, 0, 0, 0, 0]
    elif text == "This is a test.":
        return [0, 1, 0, 0, 0]
    elif text == "This is another test.":
        return [0, 0, 1, 0, 0]
    elif text == "This is a test v2.":
        return [0, 0, 0, 1, 0]
    elif text == "foo bar":
        return [0, 0, 1, 0, 0]
    elif text == "apple orange":
        return [0, 1, 0, 0, 0]
    elif text == "toronto london":
        return [1, 0, 0, 0, 0]
    elif text == "cat dog":
        return [0, 0, 0, 1, 0]
    else:
        raise ValueError("Invalid text for `mock_get_text_embedding`.")


def mock_get_text_embeddings(texts: List[str]) -> List[List[float]]:
    """Mock get text embeddings."""
    return [mock_get_text_embedding(text) for text in texts]


@patch.object(TokenTextSplitter, "split_text", side_effect=mock_token_splitter_newline)
@patch.object(LLMPredictor, "predict", side_effect=mock_llmpredictor_predict)
@patch.object(LLMPredictor, "total_tokens_used", return_value=0)
@patch.object(LLMPredictor, "__init__", return_value=None)
@patch.object(
    OpenAIEmbedding, "_get_text_embedding", side_effect=mock_get_text_embedding
)
@patch.object(
    OpenAIEmbedding, "_get_text_embeddings", side_effect=mock_get_text_embeddings
)
@patch.object(
    OpenAIEmbedding, "get_query_embedding", side_effect=mock_get_query_embedding
)
def test_recursive_query_vector_table(
    _mock_query_embed: Any,
    _mock_get_text_embeds: Any,
    _mock_get_text_embed: Any,
    _mock_init: Any,
    _mock_total_tokens_used: Any,
    _mock_predict: Any,
    _mock_split_text: Any,
    documents: List[Document],
    struct_kwargs: Dict,
) -> None:
    """Test query."""
    index_kwargs, query_configs = struct_kwargs
    vector_kwargs = index_kwargs["vector"]
    table_kwargs = index_kwargs["table"]
    # try building a tree for a group of 4, then a list
    # use a diff set of documents
    # try building a list for every two, then a tree
    list1 = GPTSimpleVectorIndex.from_documents(documents[0:2], **vector_kwargs)
    list2 = GPTSimpleVectorIndex.from_documents(documents[2:4], **vector_kwargs)
    list3 = GPTSimpleVectorIndex.from_documents(documents[4:6], **vector_kwargs)
    list4 = GPTSimpleVectorIndex.from_documents(documents[6:8], **vector_kwargs)

    summaries = [
        "foo bar",
        "apple orange",
        "toronto london",
        "cat dog",
    ]

    graph = ComposableGraph.from_indices(
        GPTSimpleKeywordTableIndex,
        [list1, list2, list3, list4],
        index_summaries=summaries,
        **table_kwargs
    )
    assert isinstance(graph, ComposableGraph)
    query_str = "Foo?"
    response = graph.query(query_str, query_configs=query_configs)
    assert str(response) == ("Foo?:Foo?:This is another test.")
    query_str = "Orange?"
    response = graph.query(query_str, query_configs=query_configs)
    assert str(response) == ("Orange?:Orange?:This is a test.")
    query_str = "Cat?"
    response = graph.query(query_str, query_configs=query_configs)
    assert str(response) == ("Cat?:Cat?:This is a test v2.")

    # test serialize and then back
    # use composable graph struct
    with TemporaryDirectory() as tmpdir:
        graph.save_to_disk(str(Path(tmpdir) / "tmp.json"))
        graph = ComposableGraph.load_from_disk(str(Path(tmpdir) / "tmp.json"))
        response = graph.query(query_str, query_configs=query_configs)
        assert str(response) == ("Cat?:Cat?:This is a test v2.")


@patch.object(TokenTextSplitter, "split_text", side_effect=mock_token_splitter_newline)
@patch.object(LLMPredictor, "predict", side_effect=mock_llmpredictor_predict)
@patch.object(LLMPredictor, "total_tokens_used", return_value=0)
@patch.object(LLMPredictor, "__init__", return_value=None)
@patch.object(
    OpenAIEmbedding, "_get_text_embedding", side_effect=mock_get_text_embedding
)
@patch.object(
    OpenAIEmbedding, "_get_text_embeddings", side_effect=mock_get_text_embeddings
)
@patch.object(
    OpenAIEmbedding, "get_query_embedding", side_effect=mock_get_query_embedding
)
def test_recursive_query_vector_table_query_configs(
    _mock_query_embed: Any,
    _mock_get_text_embeds: Any,
    _mock_get_text_embed: Any,
    _mock_init: Any,
    _mock_total_tokens_used: Any,
    _mock_predict: Any,
    _mock_split_text: Any,
    documents: List[Document],
    struct_kwargs: Dict,
) -> None:
    """Test query.

    Difference with above test is we specify query config params and
    assert that they're passed in.

    """
    index_kwargs, _ = struct_kwargs
    query_configs = [
        QueryConfig(
            index_struct_type=IndexStructType.KEYWORD_TABLE,
            query_mode=QueryMode.DEFAULT,
            query_kwargs={
                "query_keyword_extract_template": MOCK_QUERY_KEYWORD_EXTRACT_PROMPT,
                "text_qa_template": MOCK_TEXT_QA_PROMPT,
                "refine_template": MOCK_REFINE_PROMPT,
            },
        ),
        QueryConfig(
            index_struct_id="vector1",
            index_struct_type=IndexStructType.DICT,
            query_mode=QueryMode.DEFAULT,
            query_kwargs={
                "text_qa_template": MOCK_TEXT_QA_PROMPT,
                "refine_template": MOCK_REFINE_PROMPT,
                "similarity_top_k": 2,
                "required_keywords": ["v2"],
            },
        ),
        QueryConfig(
            index_struct_id="vector2",
            index_struct_type=IndexStructType.DICT,
            query_mode=QueryMode.DEFAULT,
            query_kwargs={
                "text_qa_template": MOCK_TEXT_QA_PROMPT,
                "refine_template": MOCK_REFINE_PROMPT,
                "similarity_top_k": 2,
                "required_keywords": ["world"],
            },
        ),
    ]

    vector_kwargs = index_kwargs["vector"]
    table_kwargs = index_kwargs["table"]
    # try building a tre for a group of 4, then a list
    # use a diff set of documents
    # try building a list for every two, then a tree
    list1 = GPTSimpleVectorIndex.from_documents(documents[0:2], **vector_kwargs)
    list2 = GPTSimpleVectorIndex.from_documents(documents[2:4], **vector_kwargs)
    assert isinstance(list1.index_struct, V2IndexStruct)
    assert isinstance(list2.index_struct, V2IndexStruct)
    list1.index_struct.index_id = "vector1"
    list2.index_struct.index_id = "vector2"
    summaries = [
        "foo bar",
        "apple orange",
    ]

    graph = ComposableGraph.from_indices(
        GPTSimpleKeywordTableIndex,
        [list1, list2],
        index_summaries=summaries,
        **table_kwargs
    )
    assert isinstance(graph, ComposableGraph)
    query_str = "Foo?"
    response = graph.query(query_str, query_configs=query_configs)  # type: ignore
    assert str(response) == ("Foo?:Foo?:This is a test v2.")
    query_str = "Orange?"
    response = graph.query(query_str, query_configs=query_configs)  # type: ignore
    assert str(response) == ("Orange?:Orange?:Hello world.")

    # test serialize and then back
    # use composable graph struct
    with TemporaryDirectory() as tmpdir:
        graph.save_to_disk(str(Path(tmpdir) / "tmp.json"))
        graph = ComposableGraph.load_from_disk(str(Path(tmpdir) / "tmp.json"))
        # cast to Any to avoid mypy error
        response = graph.query(query_str, query_configs=cast(Any, query_configs))
        assert str(response) == ("Orange?:Orange?:Hello world.")


@patch.object(TokenTextSplitter, "split_text", side_effect=mock_token_splitter_newline)
@patch.object(LLMPredictor, "predict", side_effect=mock_llmpredictor_predict)
@patch.object(LLMPredictor, "total_tokens_used", return_value=0)
@patch.object(LLMPredictor, "__init__", return_value=None)
@patch.object(
    OpenAIEmbedding, "_get_text_embedding", side_effect=mock_get_text_embedding
)
@patch.object(
    OpenAIEmbedding, "_get_text_embeddings", side_effect=mock_get_text_embeddings
)
@patch.object(
    OpenAIEmbedding, "get_query_embedding", side_effect=mock_get_query_embedding
)
def test_recursive_query_vector_table_async(
    _mock_query_embed: Any,
    _mock_get_text_embeds: Any,
    _mock_get_text_embed: Any,
    _mock_init: Any,
    _mock_total_tokens_used: Any,
    _mock_predict: Any,
    _mock_split_text: Any,
    documents: List[Document],
    struct_kwargs: Dict,
) -> None:
    """Test async query of table index over vector indices."""
    index_kwargs, query_configs = struct_kwargs
    vector_kwargs = index_kwargs["vector"]
    table_kwargs = index_kwargs["table"]
    # try building a tree for a group of 4, then a list
    # use a diff set of documents
    # try building a list for every two, then a tree
    list1 = GPTSimpleVectorIndex.from_documents(documents[0:2], **vector_kwargs)
    list2 = GPTSimpleVectorIndex.from_documents(documents[2:4], **vector_kwargs)
    list3 = GPTSimpleVectorIndex.from_documents(documents[4:6], **vector_kwargs)
    list4 = GPTSimpleVectorIndex.from_documents(documents[6:8], **vector_kwargs)

    summaries = [
        "foo bar",
        "apple orange",
        "toronto london",
        "cat dog",
    ]

    graph = ComposableGraph.from_indices(
        GPTSimpleKeywordTableIndex,
        [list1, list2, list3, list4],
        index_summaries=summaries,
        **table_kwargs
    )
    assert isinstance(graph, ComposableGraph)

    query_str = "Cat?"
    task = graph.aquery(query_str, query_configs=query_configs)
    response = asyncio.run(task)
    assert str(response) == ("Cat?:Cat?:This is a test v2.")


@patch.object(TokenTextSplitter, "split_text", side_effect=mock_token_splitter_newline)
@patch.object(LLMPredictor, "predict", side_effect=mock_llmpredictor_predict)
@patch.object(LLMPredictor, "total_tokens_used", return_value=0)
@patch.object(LLMPredictor, "__init__", return_value=None)
@patch.object(
    OpenAIEmbedding, "_get_text_embedding", side_effect=mock_get_text_embedding
)
@patch.object(
    OpenAIEmbedding, "_get_text_embeddings", side_effect=mock_get_text_embeddings
)
@patch.object(
    OpenAIEmbedding, "get_query_embedding", side_effect=mock_get_query_embedding
)
def test_recursive_query_vector_vector(
    _mock_query_embed: Any,
    _mock_get_text_embeds: Any,
    _mock_get_text_embed: Any,
    _mock_init: Any,
    _mock_total_tokens_used: Any,
    _mock_predict: Any,
    _mock_split_text: Any,
    documents: List[Document],
    struct_kwargs: Dict,
) -> None:
    """Test query."""
    index_kwargs, query_configs = struct_kwargs
    vector_kwargs = index_kwargs["vector"]
    # try building a tree for a group of 4, then a list
    # use a diff set of documents
    # try building a list for every two, then a tree
    list1 = GPTSimpleVectorIndex.from_documents(documents[0:2], **vector_kwargs)
    list2 = GPTSimpleVectorIndex.from_documents(documents[2:4], **vector_kwargs)
    list3 = GPTSimpleVectorIndex.from_documents(documents[4:6], **vector_kwargs)
    list4 = GPTSimpleVectorIndex.from_documents(documents[6:8], **vector_kwargs)

    summary1 = "foo bar"
    summary2 = "apple orange"
    summary3 = "toronto london"
    summary4 = "cat dog"
    summaries = [summary1, summary2, summary3, summary4]

    graph = ComposableGraph.from_indices(
        GPTSimpleVectorIndex,
        [list1, list2, list3, list4],
        index_summaries=summaries,
        **vector_kwargs
    )
    query_str = "Foo?"
    response = graph.query(query_str, query_configs=query_configs)
    assert str(response) == ("Foo?:Foo?:This is another test.")
    query_str = "Orange?"
    response = graph.query(query_str, query_configs=query_configs)
    assert str(response) == ("Orange?:Orange?:This is a test.")
    query_str = "Cat?"
    response = graph.query(query_str, query_configs=query_configs)
    assert str(response) == ("Cat?:Cat?:This is a test v2.")

    # test serialize and then back
    # use composable graph struct
    with TemporaryDirectory() as tmpdir:
        graph.save_to_disk(str(Path(tmpdir) / "tmp.json"))
        graph = ComposableGraph.load_from_disk(str(Path(tmpdir) / "tmp.json"))
        response = graph.query(query_str, query_configs=query_configs)
        assert str(response) == ("Cat?:Cat?:This is a test v2.")
