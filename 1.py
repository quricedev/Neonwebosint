from flask import Flask, request, jsonify, render_template_string, send_from_directory
from dotenv import load_dotenv
import requests, re, os, json, zipfile
import pyfiglet

load_dotenv()
app = Flask(__name__)
API_URL = os.getenv("API_URL")



def exfv():
    zip_path = os.path.join(app.root_path, "favicon_io.zip")
    target_dir = os.path.join(app.root_path, "static/icons")

    if not os.path.exists(zip_path):
        return

    if not os.path.exists(target_dir):
        os.makedirs(target_dir, exist_ok=True)
        with zipfile.ZipFile(zip_path, 'r') as z:
            z.extractall(target_dir)
        print("Favicons extracted!")
    else:
        print("Favicons already extracted.")


exfv()



def normie_num(raw: str):
    digits = re.sub(r"\D", "", raw)

    if len(digits) == 10:
        num = digits
    elif len(digits) == 11 and digits.startswith("0"):
        num = digits[1:]
    elif len(digits) == 12 and digits.startswith("91"):
        num = digits[2:]
    elif len(digits) == 13 and digits.startswith("0091"):
        num = digits[4:]
    elif len(digits) > 10 and digits[-10:].startswith(("6", "7", "8", "9")):
        num = digits[-10:]
    else:
        return None

    return num if re.match(r"^[6-9]\d{9}$", num) else None


@app.route("/")
def index():
    return render_template_string("""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Neon OSINT</title>

<link rel="icon" type="image/x-icon" href="/static/icons/favicon.ico">
<script src="https://cdn.tailwindcss.com"></script>

<style>
body {
  background:#0f172a; color:#f1f5f9;
  font-family:'Inter',sans-serif;
}
.card {
  background:#1e293b;
  border-radius:1rem;
  padding:2rem;
  box-shadow:0 0 20px rgba(0,0,0,.3);
  border:2px solid transparent;
  animation: borderGlow 2s linear infinite;
}
@keyframes borderGlow {
  0% { border-color:#38bdf8; box-shadow:0 0 10px #38bdf8; }
  33% { border-color:#a855f7; box-shadow:0 0 15px #a855f7; }
  66% { border-color:#22c55e; box-shadow:0 0 15px #22c55e; }
  100% { border-color:#38bdf8; box-shadow:0 0 10px #38bdf8; }
}
.spinner {
  border:4px solid rgba(255,255,255,0.1);
  border-top:4px solid #38bdf8;
  border-radius:50%;
  width:40px; height:40px;
  animation: spin 1s linear infinite;
  margin:auto;
}
@keyframes spin {from{transform:rotate(0deg);}to{transform:rotate(360deg);}}
button,input{outline:none;}
pre{background:#0f172a;padding:1rem;border-radius:.75rem;overflow-x:auto;}
</style>
</head>

<body class="flex flex-col items-center justify-center min-h-screen px-4">

  <h1 class="text-4xl font-bold mb-1 text-blue-400">NEON OSINT 🔍</h1>
  <h3 class="text-gray-400 mb-6 text-lg">Number to Information Tool</h3>

  <div class="card w-full max-w-lg">

    <form id="lookupForm" class="flex flex-col gap-4 mt-4">
      <input id="number" name="number" class="w-full p-3 rounded-lg bg-slate-700 text-white"
       placeholder="Enter Number. (Ex/~ +911234567890)" required>

      <button type="submit"
       class="bg-blue-600 hover:bg-blue-700 transition text-white font-semibold py-2 rounded-lg">
       Search
      </button>
    </form>

    <div id="loading" class="hidden mt-6 flex flex-col items-center gap-2">
      <div class="spinner"></div>
      <p class="text-gray-400">Fetching data Please wait...</p>
    </div>

    <div id="result" class="mt-6 hidden">
      <div class="flex justify-between items-center mb-2 gap-2">
        <h2 class="text-lg font-semibold">Result:</h2>
        <div class="flex gap-2">
          <button id="copyBtn"
           class="bg-green-600 hover:bg-green-700 px-3 py-1 rounded text-white text-sm hidden">
           Copy DATA
          </button>
          <button id="downloadBtn"
           class="bg-purple-600 hover:bg-purple-700 px-3 py-1 rounded text-white text-sm hidden">
           Download DATA
          </button>
        </div>
      </div>
      <pre id="output"></pre>
    </div>

  </div>

  <p class="mt-6 text-gray-500 text-sm">© Vishwas OSINT Tool™ </p>

<script>
const form=document.getElementById("lookupForm");
const output=document.getElementById("output");
const result=document.getElementById("result");
const copyBtn=document.getElementById("copyBtn");
const downloadBtn=document.getElementById("downloadBtn");
const loading=document.getElementById("loading");

form.addEventListener("submit",async(e)=>{
  e.preventDefault();
  const number=document.getElementById("number").value.trim();
  result.classList.add("hidden");
  loading.classList.remove("hidden");
  copyBtn.classList.add("hidden");
  downloadBtn.classList.add("hidden");

  try{
    const res=await fetch("/lookup",{
      method:"POST",
      headers:{"Content-Type":"application/x-www-form-urlencoded"},
      body:`number=${encodeURIComponent(number)}`
    });

    const data=await res.json();
    const { Channel, ...cleaned } = data;
    const finalData = { "Details by": "Neon OSINT", ...cleaned };
    const formatted=JSON.stringify(finalData,null,2);
    output.textContent=formatted;

    loading.classList.add("hidden");
    result.classList.remove("hidden");
    copyBtn.classList.remove("hidden");
    downloadBtn.classList.remove("hidden");

  }catch(err){
    output.textContent="Error fetching data.";
    loading.classList.add("hidden");
    result.classList.remove("hidden");
  }
});

copyBtn.addEventListener("click",()=>{
  navigator.clipboard.writeText(output.textContent)
    .then(()=>{
      copyBtn.textContent="Copied!";
      setTimeout(()=>copyBtn.textContent="Copy JSON",2000);
    });
});

downloadBtn.addEventListener("click",()=>{
  const blob=new Blob([output.textContent],{type:"application/json"});
  const url=URL.createObjectURL(blob);
  const a=document.createElement("a");
  a.href=url; a.download="neon_osint_result.json";
  a.click(); URL.revokeObjectURL(url);
});
</script>

</body>
</html>
""")


@app.route("/lookup", methods=["POST"])
def lookup():
    raw = request.form.get("number", "")
    num = normie_num(raw)

    if not num:
        return jsonify({"error": "Invalid number format"}), 400

    url = API_URL.format(num=num)

    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()

        data = r.json()
        
        
        if "Channel" in data:
        	del data["Channel"]

        return jsonify(data)
        
    except requests.exceptions.Timeout:
        return jsonify({"error": "The Neon OSINT server may be busy. Please try again.."}), 504
    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500



@app.route("/favicon.ico")
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, "static/icons"),
        "favicon.ico",
        mimetype="image/vnd.microsoft.icon"
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)


ascii_art = pyfiglet.figlet_format("INDia", font="isometric1")
print(ascii_art)
