import os
import re
from typing import List
from django.conf import settings
from groq import Groq

# Common English stopwords to ignore during relevance scoring
STOPWORDS = {
    'a', 'about', 'above', 'after', 'again', 'against', 'all', 'am', 'an', 'and',
    'any', 'are', 'aren', 'as', 'at', 'be', 'because', 'been', 'before', 'being',
    'below', 'between', 'both', 'but', 'by', 'can', 'cannot', 'could', 'couldn',
    'did', 'didn', 'do', 'does', 'doesn', 'doing', 'don', 'down', 'during', 'each',
    'few', 'for', 'from', 'further', 'had', 'hadn', 'has', 'hasn', 'have', 'haven',
    'having', 'he', 'her', 'here', 'hers', 'herself', 'him', 'himself', 'his',
    'how', 'i', 'if', 'in', 'into', 'is', 'isn', 'it', 'its', 'itself', 'just',
    'me', 'more', 'most', 'mustn', 'my', 'myself', 'no', 'nor', 'not', 'now', 'of',
    'off', 'on', 'once', 'only', 'or', 'other', 'our', 'ours', 'ourselves', 'out',
    'over', 'own', 'same', 'shan', 'she', 'should', 'shouldn', 'so', 'some', 'such',
    'than', 'that', 'the', 'their', 'theirs', 'them', 'themselves', 'then', 'there',
    'these', 'they', 'this', 'those', 'through', 'to', 'too', 'under', 'until', 'up',
    'very', 'was', 'wasn', 'we', 'were', 'weren', 'what', 'when', 'where', 'which',
    'while', 'who', 'whom', 'why', 'will', 'with', 'won', 'would', 'wouldn', 'you',
    'your', 'yours', 'yourself', 'yourselves'
}


def chunk_text(text: str, chunk_size: int = 500) -> List[str]:
    """
    Splits a document's extracted text into overlapping word chunks of roughly chunk_size words each.
    Returns an empty list if text is empty, None, or whitespace.
    """
    if not text:
        return []

    words = text.split()
    if not words:
        return []

    if chunk_size <= 0:
        chunk_size = 500

    total_words = len(words)
    if total_words <= chunk_size:
        return [' '.join(words)]

    # Overlap by ~10% or up to 50 words
    overlap = min(50, chunk_size // 2) if chunk_size > 1 else 0
    step = max(1, chunk_size - overlap)

    chunks = []
    i = 0
    while i < total_words:
        chunk_words = words[i:i + chunk_size]
        if chunk_words:
            chunks.append(' '.join(chunk_words))
        if i + chunk_size >= total_words:
            break
        i += step

    return chunks


def get_relevant_chunks(question: str, chunks: List[str], top_n: int = 3) -> List[str]:
    """
    Scores each chunk by how many of the question's significant words appear in it,
    ignoring common stopwords, and returns the top_n highest scoring chunks.
    """
    if not question or not chunks:
        return []

    if top_n <= 0:
        return []

    # Extract alphanumeric words in lowercase
    q_tokens = re.findall(r'\b\w+\b', question.lower())
    significant_words = [token for token in q_tokens if token not in STOPWORDS]

    # Fallback to all question tokens if only stopwords were provided
    if not significant_words:
        significant_words = q_tokens

    if not significant_words:
        return chunks[:top_n]

    scored_chunks = []
    for idx, chunk in enumerate(chunks):
        chunk_lower = chunk.lower()
        chunk_tokens = re.findall(r'\b\w+\b', chunk_lower)
        chunk_token_set = set(chunk_tokens)

        # Count total matches and distinct keyword matches
        total_matches = sum(chunk_tokens.count(w) for w in significant_words)
        distinct_matches = sum(1 for w in significant_words if w in chunk_token_set)

        scored_chunks.append((total_matches, distinct_matches, -idx, chunk))

    # Sort descending by match score and distinct count
    scored_chunks.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)

    return [item[3] for item in scored_chunks[:top_n]]


def ask_document(document, question: str) -> str:
    """
    Answers a question about a document using relevant excerpts and Groq's chat completion API.
    If no extracted text is available, returns a friendly message without calling the API.
    Handles API errors gracefully.
    """
    if not document or not document.current_version or not document.current_version.extracted_text or not document.current_version.extracted_text.strip():
        return "No readable text is available for this document."

    extracted_text = document.current_version.extracted_text.strip()
    chunks = chunk_text(extracted_text, chunk_size=500)
    if not chunks:
        return "No readable text is available for this document."

    relevant_chunks = get_relevant_chunks(question, chunks, top_n=3)
    if not relevant_chunks:
        return "No readable text is available for this document."

    context_text = "\n\n---\n\n".join(relevant_chunks)

    api_key = getattr(settings, 'GROQ_API_KEY', '') or os.environ.get('GROQ_API_KEY', '')

    try:
        client = Groq(api_key=api_key)
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant for Kochi Metro document analysis. "
                    "Answer the question strictly using only the provided document excerpts below. "
                    "If the answer is not in the provided excerpts, say clearly that the answer "
                    "is not found in the document excerpts."
                ),
            },
            {
                "role": "user",
                "content": f"Document excerpts:\n{context_text}\n\nQuestion: {question}",
            },
        ]
        chat_completion = client.chat.completions.create(
            messages=messages,
            model="openai/gpt-oss-120b",
        )
        reply = chat_completion.choices[0].message.content
        return reply.strip() if reply else "No response received from the AI service."
    except Exception as e:
        return f"Unable to process question with the AI service at this time. Please try again later."

