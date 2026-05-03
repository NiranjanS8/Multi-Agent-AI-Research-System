from langchain.agents import create_agent
from langchain_mistralai import ChatMistralAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from app.tools import web_search, web_scrap
from dotenv import load_dotenv
import os


def get_llm():
    load_dotenv(override=True)
    return ChatMistralAI(
        model=os.getenv("MISTRAL_MODEL", "mistral-small-latest"),
        temperature=0,
        max_tokens=1200,
    )

def build_search_agent():
    return create_agent(
        model=get_llm(),
        tools=[web_search]
    )

def build_web_scrap_agent():
    return create_agent(
        model=get_llm(),
        tools=[web_scrap]
    )

writer_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are an expert research writer. Write clear, structured and insightful reports."),
    ("human", """Write a detailed research report on the topic below.

Topic: {topic}

Research Gathered:
{research}

Format the report in clean Markdown:
## Introduction
Write 1-2 concise paragraphs. Include citation markers like [1] or [2] for factual claims.

## Key Findings
- Include at least 3 well-explained bullet points.
- Bold the most important phrase at the start of each bullet.
- Add citation markers to each source-backed bullet.

## Conclusion
Write a clear synthesis of the research.

## Sources
- List cited sources in this format: [1] Source title - URL.

Be detailed, factual and professional.""")
])

def build_writer_chain():
    return writer_prompt | get_llm() | StrOutputParser()

critic_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a strict and detail-oriented research reviewer. Your job is to critique and improve reports."),
    ("human", """Review the following research report carefully.

Report:
{report}

Evaluate it based on:
- Clarity and structure
- Depth and accuracy
- Completeness of key findings
- Logical flow
- Quality of sources

Keep the critique medium-length, practical, and fast to read. Do not rewrite the full report.

Format your response in clean Markdown:
## Weaknesses
- Give 3-5 specific weaknesses. Be critical and precise.

## Suggestions
- Give 3-5 concrete improvements.

## Improved Summary
Write one improved 120-180 word summary that shows how the report could be strengthened.

Be honest, analytical, and constructive. Stay under 450 words total.""")
])

def build_critic_chain():
    return critic_prompt | get_llm() | StrOutputParser()

