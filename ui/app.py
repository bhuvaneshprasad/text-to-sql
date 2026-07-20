import os

import chainlit as cl
import httpx

API_URL = os.getenv("CHAT_API_URL", "http://localhost:8000/api/v1/chat/")

# I do not have a GPU, hence have set a higher timeout
TIMEOUT = httpx.Timeout(connect=10.0, read=600.0, write=10.0, pool=10.0)

MAX_CHAT_TURNS = 7


@cl.on_chat_start
async def on_chat_start():
    cl.user_session.set("history", [])
    await cl.Message(
        content="What’s on your mind today?"
    ).send()


@cl.on_message
async def on_message(message: cl.Message):
    history = cl.user_session.get("history", [])
    thinking = cl.Message(content="")
    await thinking.send()

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(API_URL, json={"question": message.content, "history": history})
            resp.raise_for_status()
            data = resp.json()
        response = data.get("response", "(empty response)")
        thinking.content = response

        history.append({"role": "user", "content": message.content})
        history.append({"role": "assistant", "content": response})
        cl.user_session.set("history", history[-MAX_CHAT_TURNS *2:])
    except httpx.HTTPStatusError as exc:
        thinking.content = f"API error {exc.response.status_code}: {exc.response.text}"
    except httpx.RequestError as exc:
        thinking.content = f"Could not reach the API at {API_URL}: {exc}"

    await thinking.update()
