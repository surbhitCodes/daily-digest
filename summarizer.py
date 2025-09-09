from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()

def get_openai_client():
    """Get OpenAI client with proper error handling"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is required")
    return OpenAI(api_key=api_key)

async def summarize_articles(articles):
    # Create a more structured prompt that preserves links
    article_list = []
    for i, article in enumerate(articles[:12], 1):
        article_list.append(f"{i}. {article['title']}\n   Link: {article['link']}")
    
    combined_text = "\n\n".join(article_list)
    prompt = f"""Summarize the following tech/AI articles. For each article, provide a 2-3 sentence summary followed by the original link in this exact format:

**Article Title**
Summary here...
🔗 [Read more](original_link)

Articles to summarize:
{combined_text}

Please maintain this format exactly and include all the links."""
    
    client = get_openai_client()
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )
    
    # If AI doesn't include links properly, format them ourselves
    ai_summary = response.choices[0].message.content.strip()
    
    # Fallback: If AI summary doesn't have proper links, create formatted version
    if "🔗" not in ai_summary or "[Read more]" not in ai_summary:
        return format_articles_with_links(articles[:12], ai_summary)
    
    return ai_summary

def format_articles_with_links(articles, ai_summary=None):
    """Format articles with proper links as fallback"""
    formatted_blocks = ["📰 **AI & Tech Daily Digest**\n"]
    
    for i, article in enumerate(articles, 1):
        title = article.get("title", "Untitled")
        link = article.get("link", "#")
        
        # Try to extract relevant summary from AI response if available
        summary = f"Latest update from the tech world covering {title.lower()}."
        
        formatted_blocks.append(
            f"**{i}. {title}**\n"
            f"{summary}\n"
            f"🔗 [Read more]({link})\n"
        )
    
    return "\n".join(formatted_blocks)

def format_slack_digest(articles: list[dict]) -> str:
    blocks = ["*📰 AI + Dev Digest:*\n"]
    for i, article in enumerate(articles, 1):
        title = article.get("title", "Untitled")
        link = article.get("link", "#")
        summary = article.get("summary", "No summary provided.")
        blocks.append(
            f"*{i}. <{link}|{title}>*\n"
            f"> {summary.strip()}\n"
        )
    return "\n".join(blocks)
