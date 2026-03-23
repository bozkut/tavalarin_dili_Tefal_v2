#!/usr/bin/env python
"""Debug version to see what Claude returns"""

import os
import json
from base64 import b64encode
import anthropic

os.environ["ANTHROPIC_API_KEY"] = "REDACTED"

# İlk panı test et
test_image = r"E:\Tefal\Görseller\Tavalar\484809144_651713074128278_7864583726765487524_n.jpg"

with open(test_image, "rb") as f:
    image_data = b64encode(f.read()).decode("utf-8")

client = anthropic.Anthropic()

prompt = """You are analyzing scratch patterns on a non-stick pan surface.
Look carefully at the scratches and find letter shapes (A–Z, a–z).
You may combine multiple scratches to form a single letter.
You do NOT need to find all letters — only report ones you are confident about.

For each letter found, return normalized coordinates (0.0–1.0 relative to image width/height)
that trace the strokes of the letter shape over the scratches.

Respond with ONLY a JSON object in this format:
{
  "letters": [
    {
      "letter": "B",
      "confidence": "high",
      "strokes": [
        [[x1,y1],[x2,y2],[x3,y3]],
        [[x4,y4],[x5,y5]]
      ]
    }
  ]
}

confidence can be "high", "medium", or "low".
Each stroke is a list of [x,y] normalized points forming one continuous line segment.
If no letters are found, return: {"letters": []}"""

try:
    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2048,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_data,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    )

    response_text = message.content[0].text
    print("=" * 60)
    print("RAW RESPONSE:")
    print(response_text)
    print("=" * 60)

    # JSON olarak parse etmeye çalış
    try:
        result = json.loads(response_text)
        print("✓ JSON başarıyla parse edildi:")
        print(json.dumps(result, indent=2))
    except json.JSONDecodeError as e:
        print(f"✗ JSON parse hatası: {e}")
        print(f"   Hatanın başladığı yer: char {e.pos}")

except Exception as e:
    print(f"✗ API hatası: {e}")
