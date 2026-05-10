import requests

API_KEY = "53606838643effa64a54a7c7148b0d560e12d90961fa715376eddf34b362aeab"
mmsi = 353136000

response = requests.get(
    f"https://api.vesselapi.com/v1/vessel/{mmsi}/history",
    headers={"Authorization": f"Bearer {API_KEY}"}
)

print(response.status_code)
print(response.text)  # raw response, no parsing