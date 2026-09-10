from flask import Flask, render_template_string, request, jsonify
import sqlite3
import datetime

app = Flask(__name__)
DB_FILE = "attendance.db"

# === DATABASE SETUP ===
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS lists (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        list_name TEXT NOT NULL UNIQUE
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        list_id INTEGER NOT NULL,
        student_number TEXT NOT NULL UNIQUE,
        full_name TEXT NOT NULL,
        FOREIGN KEY (list_id) REFERENCES lists(id)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_number TEXT NOT NULL,
        time_in TEXT,
        time_out TEXT,
        scan_date TEXT NOT NULL
    )""")
    conn.commit()
    conn.close()

init_db()

# === MAIN PAGE — DALAWANG BAHAGI LANG: STUDENT LIST + SCAN ID ===
@app.route('/')
def index():
    return render_template_string('''
<!DOCTYPE html>
<html>
<head>
    <title>Attendance Scanner</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
</head>
<body>

    <!-- ================================== -->
    <!-- PART 1: STUDENT LIST -->
    <!-- ================================== -->
    <h1>Student List</h1>

    <h3>Create New List</h3>
    <input type="text" id="new-list" placeholder="Type list name...">
    <button onclick="addList()">Create List</button>
    <p id="list-msg"></p>

    <h3>Select List</h3>
    <select id="list-select" onchange="loadStudents()">
        <option value="">-- Choose List --</option>
    </select>
    <hr>

    <h4>Add Student</h4>
    <input type="text" id="new-num" placeholder="Student Number">
    <input type="text" id="new-name" placeholder="Full Name">
    <button onclick="addStudent()">Add Student</button>
    <p id="student-msg"></p>

    <h3>Students in List</h3>
    <table border="1">
        <tr><th>Student Number</th><th>Name</th></tr>
        <tbody id="student-list"></tbody>
    </table>

    <hr>

    <!-- ================================== -->
    <!-- PART 2: SCAN ID -->
    <!-- ================================== -->
    <h1>Scan ID</h1>
    <div id="video"></div>
    <p id="scan-result"></p>
    <input type="text" id="manual-scan" placeholder="Or type Student Number">
    <button onclick="manualScan()">Submit</button>

<script src="https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js"></script>
<script>
let scanner;

// === START CAMERA ===
function startScanner() {
    scanner = new Html5Qrcode("video");
    scanner.start(
        { facingMode: "environment" },
        { fps: 10 },
        (decodedText) => {
            scanner.pause();
            processScan(decodedText);
            setTimeout(() => scanner.resume(), 2000);
        },
        () => {}
    ).catch(err => {
        document.getElementById("video").innerHTML = "<p>Camera not available. Type manually.</p>";
    });
}

// === CREATE NEW LIST ===
async function addList() {
    const name = document.getElementById("new-list").value.trim();
    const msg = document.getElementById("list-msg");
    if (!name) { msg.innerText = "Type a list name!"; return; }

    const res = await fetch('/add_list', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({list_name: name})
    });
    const data = await res.json();
    msg.innerText = data.message;
    document.getElementById("new-list").value = "";
    loadLists();
}

// === LOAD ALL LISTS ===
async function loadLists() {
    const res = await fetch('/lists');
    const data = await res.json();
    const sel = document.getElementById("list-select");
    sel.innerHTML = '<option value="">-- Choose List --</option>';
    data.lists.forEach(l => {
        sel.innerHTML += <option value="${l[0]}">${l[1]}</option>;
    });
}

// === ADD STUDENT TO SELECTED LIST ===
async function addStudent() {
    const listId = document.getElementById("list-select").value;
    const num = document.getElementById("new-num").value.trim();
    const name = document.getElementById("new-name").value.trim();
    const msg = document.getElementById("student-msg");

    if (!listId) { msg.innerText = "Select a list first!"; return; }
    if (!num || !name) { msg.innerText = "Fill in both fields!"; return; }

    const res = await fetch('/add_student', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({list_id: listId, student_number: num, full_name: name})
    });
    const data = await res.json();
    msg.innerText = data.message;
    document.getElementById("new-num").value = "";
    document.getElementById("new-name").value = "";
    loadStudents();
}

// === LOAD STUDENTS OF SELECTED LIST ===
async function loadStudents() {
    const listId = document.getElementById("list-select").value;
    const tbody = document.getElementById("student-list");
    if (!listId) { tbody.innerHTML = ""; return; }

    const res = await fetch(/students?list_id=${listId});
    const data = await res.json();
    tbody.innerHTML = "";
    data.students.forEach(s => {
        tbody.innerHTML += <tr><td>${s[2]}</td><td>${s[3]}</td></tr>;
    });
}

// === PROCESS SCAN — AUTO ATTENDANCE ===
async function processScan(studentNumber) {
    const res = await fetch('/scan', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({student_number: studentNumber})
    });
    const data = await res.json();
    document.getElementById("scan-result").innerText = data.message;
}

// === MANUAL INPUT ===
function manualScan() {
    const num = document.getElementById("manual-scan").value.trim();
    if (num) processScan(num);
    document.getElementById("manual-scan").value = "";
}

// === LOAD ON START ===
window.onload = function() {
    loadLists();
    startScanner();
};
</script>
</body>
</html>
    ''')

# === CREATE LIST ===
@app.route('/add_list', methods=['POST'])
def add_list():
    data = request.get_json()
    name = data.get('list_name', '').strip()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO lists (list_name) VALUES (?)", (name,))
        conn.commit()
        msg = f"List created: {name}"
    except sqlite3.IntegrityError:
        msg = "List name already exists!"
    conn.close()
    return jsonify({"message": msg})

# === GET ALL LISTS ===
@app.route('/lists')
def lists():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM lists ORDER BY id")
    data = c.fetchall()
    conn.close()
    return jsonify({"lists": data})

# === ADD STUDENT ===
@app.route('/add_student', methods=['POST'])
def add_student():
    data = request.get_json()
    list_id = data.get('list_id')
    num = data.get('student_number', '').strip()
    name = data.get('full_name', '').strip()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO students (list_id, student_number, full_name) VALUES (?, ?, ?)",
                  (list_id, num, name))
        conn.commit()
        msg = f"Student added: {name}"
    except sqlite3.IntegrityError:
        msg = "Student Number already exists!"
    conn.close()
    return jsonify({"message": msg})

# === GET STUDENTS BY LIST ===
@app.route('/students')
def students():
    list_id = request.args.get('list_id')
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM students WHERE list_id = ?", (list_id,))
    data = c.fetchall()
    conn.close()
    return jsonify({"students": data})

# === SCAN — AUTO TIME IN / TIME OUT ===
@app.route('/scan', methods=['POST'])
def scan():
    data = request.get_json()
    student_number = data.get('student_number', '').strip()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("SELECT full_name FROM students WHERE student_number = ?", (student_number,))
    student = c.fetchone()
    if not student:
        conn.close()
        return jsonify({"message": "Student not found!"})

    name = student[0]
    today = datetime.date.today().isoformat()
    now = datetime.datetime.now().strftime("%H:%M")

    c.execute("SELECT id FROM attendance WHERE student_number = ? AND scan_date = ? AND time_out IS NULL",
              (student_number, today))
    active = c.fetchone()

    if active:
        c.execute("UPDATE attendance SET time_out = ? WHERE id = ?", (now, active[0]))
        msg = f"Time Out: {name} at {now}"
    else:
        c.execute("INSERT INTO attendance (student_number, time_in, scan_date) VALUES (?, ?, ?)",
                  (student_number, now, today))
        msg = f"Time In: {name} at {now}"

    conn.commit()
    conn.close()
    return jsonify({"message": msg})

if __name__ == '__main__':
    app.run(debug=True)
