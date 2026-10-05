let currentMode = "Interview";
let currentQuestion = "Tell me about yourself.";
let lastFeedback = "";

let currentAudio = null;
let isVoicePlaying = false;

const questions = {
    Interview: [
        "Tell me about yourself.",
        "What is a project you are proud of?",
        "What was the biggest challenge you faced in a project?",
        "Why should we select you?"
    ],
    Presentation: [
        "Explain a project you have worked on.",
        "Explain a difficult concept in simple words.",
        "How would you convince someone to use your project?"
    ],
    Conversation: [
        "Tell me about your day.",
        "What do you enjoy doing in your free time?",
        "Tell me about something interesting you learned recently."
    ]
};

// Initialize SpeechSynthesis voices cache
if ("speechSynthesis" in window) {
    window.speechSynthesis.onvoiceschanged = () => {
        window.speechSynthesis.getVoices();
    };
}

function escapeHtml(str) {
    if (!str) return "";
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function stopVoice() {
    if (currentAudio) {
        currentAudio.pause();
        currentAudio.currentTime = 0;
        currentAudio = null;
    }
    if ("speechSynthesis" in window) {
        window.speechSynthesis.cancel();
    }
    isVoicePlaying = false;
    updateVoiceButton(false);
}

function updateVoiceButton(playing, text) {
    const btn = document.getElementById("voiceBtn");
    if (!btn) return;
    if (playing) {
        btn.innerHTML = text || "⏹️ Stop Voice";
        btn.classList.add("playing");
    } else {
        btn.innerHTML = "🔊 Hear Feedback";
        btn.classList.remove("playing");
    }
}

function getBestVoice() {
    if (!("speechSynthesis" in window)) return null;
    const voices = window.speechSynthesis.getVoices();
    if (!voices || voices.length === 0) return null;

    // Prioritize natural English voices
    const naturalEn = voices.find(v => 
        v.lang.startsWith("en") && 
        (v.name.includes("Natural") || v.name.includes("Neural") || v.name.includes("Google") || v.name.includes("Zira") || v.name.includes("Samantha") || v.name.includes("David"))
    );
    if (naturalEn) return naturalEn;

    // Any English voice
    const anyEn = voices.find(v => v.lang.startsWith("en"));
    if (anyEn) return anyEn;

    return voices.find(v => v.default) || voices[0];
}

function speakWithBrowser(text) {
    if (!("speechSynthesis" in window)) {
        alert("Your browser does not support voice playback.");
        stopVoice();
        return;
    }

    window.speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 0.95;
    utterance.pitch = 1.0;

    const voice = getBestVoice();
    if (voice) {
        utterance.voice = voice;
    }

    utterance.onstart = () => {
        isVoicePlaying = true;
        updateVoiceButton(true, "⏹️ Stop Voice");
    };

    utterance.onend = () => {
        stopVoice();
    };

    utterance.onerror = (e) => {
        console.warn("Browser speech error:", e);
        stopVoice();
    };

    window.speechSynthesis.speak(utterance);
}

async function speakFeedback() {
    if (!lastFeedback) {
        alert("Please analyze an answer first to hear feedback.");
        return;
    }

    // Toggle stop if already speaking
    if (isVoicePlaying) {
        stopVoice();
        return;
    }

    updateVoiceButton(true, "⏳ Preparing Voice...");
    isVoicePlaying = true;

    try {
        const response = await fetch("/api/voice", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                text: lastFeedback
            })
        });

        const contentType = response.headers.get("content-type") || "";

        if (response.ok && contentType.includes("audio")) {
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            currentAudio = new Audio(url);

            currentAudio.onplay = () => {
                updateVoiceButton(true, "⏹️ Stop Voice");
            };

            currentAudio.onended = () => {
                stopVoice();
            };

            currentAudio.onerror = () => {
                console.warn("ElevenLabs audio play failed, falling back to browser voice.");
                currentAudio = null;
                speakWithBrowser(lastFeedback);
            };

            await currentAudio.play();
            return;
        }

        // If ElevenLabs is unconfigured or returns an error, seamlessly use browser speech synthesis
        speakWithBrowser(lastFeedback);

    } catch (error) {
        console.warn("Voice API error, using browser speech synthesis:", error);
        speakWithBrowser(lastFeedback);
    }
}

function changeMode(mode, button) {
    stopVoice();
    currentMode = mode;

    document.querySelectorAll(".mode").forEach(b => b.classList.remove("active"));
    button.classList.add("active");

    currentQuestion = questions[mode][0];
    document.getElementById("question").innerText = currentQuestion;
    document.getElementById("answer").value = "";
    document.getElementById("result").style.display = "none";
}

async function analyze() {
    stopVoice();

    const answer = document.getElementById("answer").value.trim();

    if (!answer) {
        alert("Please write your answer first.");
        return;
    }

    document.getElementById("loading").style.display = "block";
    document.getElementById("result").style.display = "none";

    try {
        const response = await fetch("/api/practice", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                scenario: currentMode,
                question: currentQuestion,
                answer: answer
            })
        });

        const data = await response.json();

        if (data.error) {
            alert("Analysis Error: " + data.error);
            return;
        }

        document.getElementById("clarity").innerText = data.clarity + "/10";
        document.getElementById("grammar").innerText = data.grammar + "/10";
        document.getElementById("vocabulary").innerText = data.vocabulary + "/10";
        document.getElementById("confidence").innerText = data.confidence + "/10";
        document.getElementById("overall").innerText = data.overall + "/10";

        const list = document.getElementById("suggestions");
        list.innerHTML = "";

        if (Array.isArray(data.suggestions)) {
            data.suggestions.forEach(suggestion => {
                const li = document.createElement("li");
                li.innerText = suggestion;
                list.appendChild(li);
            });
        }

        document.getElementById("followup").innerText = data.follow_up || "";

        // Build natural spoken feedback
        let speechParts = [];
        if (data.suggestions && data.suggestions.length > 0) {
            speechParts.push("Here are some improvement tips: " + data.suggestions.join(". "));
        }
        if (data.follow_up) {
            speechParts.push("Follow-up question: " + data.follow_up);
        }
        lastFeedback = speechParts.join(". ") || "Good job! Keep practicing.";

        document.getElementById("result").style.display = "block";

        // Refresh recent sessions history immediately
        loadHistory();

    } catch (error) {
        console.error("Practice error:", error);
        alert("Could not connect to SpeakBuddy.");
    } finally {
        document.getElementById("loading").style.display = "none";
    }
}

function nextQuestion() {
    stopVoice();

    const list = questions[currentMode];
    let index = list.indexOf(currentQuestion);
    index++;
    if (index >= list.length) {
        index = 0;
    }

    currentQuestion = list[index];
    document.getElementById("question").innerText = currentQuestion;
    document.getElementById("answer").value = "";
    document.getElementById("result").style.display = "none";

    window.scrollTo({
        top: 0,
        behavior: "smooth"
    });
}

function clearAnswer() {
    document.getElementById("answer").value = "";
}

function toggleSessionDetails(index, btn) {
    const detailEl = document.getElementById(`session-detail-${index}`);
    if (!detailEl) return;
    if (detailEl.style.display === "none") {
        detailEl.style.display = "block";
        btn.innerText = "Hide Details ▲";
    } else {
        detailEl.style.display = "none";
        btn.innerText = "View Feedback Details ▼";
    }
}

async function loadHistory() {
    const container = document.getElementById("history");
    if (!container) return;

    try {
        const response = await fetch("/api/history");
        const data = await response.json();

        if (data.error) {
            container.innerHTML = `<p class="muted">Could not load history: ${escapeHtml(data.error)}</p>`;
            return;
        }

        if (!Array.isArray(data) || data.length === 0) {
            container.innerHTML = `
                <p class="muted">
                    No sessions yet. Complete a practice session above to see your history.
                </p>
            `;
            return;
        }

        container.innerHTML = "";

        data.forEach((session, index) => {
            const div = document.createElement("div");
            div.className = "session";

            let dateDisplay = "";
            if (session.created_at) {
                try {
                    const d = new Date(session.created_at);
                    dateDisplay = d.toLocaleDateString(undefined, {
                        month: "short",
                        day: "numeric",
                        hour: "2-digit",
                        minute: "2-digit"
                    });
                } catch (e) {}
            }

            const feedback = session.feedback || {};
            const suggestions = feedback.suggestions || [];
            const followUp = feedback.follow_up || "";

            div.innerHTML = `
                <div class="session-top">
                    <div>
                        <strong>${escapeHtml(session.scenario || "Practice")}</strong>
                        ${dateDisplay ? `<span class="session-date">${escapeHtml(dateDisplay)}</span>` : ""}
                    </div>
                    <span class="session-score">${session.overall}/10</span>
                </div>
                <p class="session-q"><strong>Question:</strong> ${escapeHtml(session.question || "")}</p>
                ${session.answer ? `<p class="session-a"><strong>Your Answer:</strong> ${escapeHtml(session.answer)}</p>` : ""}
                <div class="session-details" id="session-detail-${index}" style="display: none;">
                    <div class="session-scores-mini">
                        <span class="mini-score">Clarity: <strong>${feedback.clarity ?? "-"}/10</strong></span>
                        <span class="mini-score">Grammar: <strong>${feedback.grammar ?? "-"}/10</strong></span>
                        <span class="mini-score">Vocabulary: <strong>${feedback.vocabulary ?? "-"}/10</strong></span>
                        <span class="mini-score">Confidence: <strong>${feedback.confidence ?? "-"}/10</strong></span>
                    </div>
                    ${suggestions.length ? `
                        <div class="session-sugg-box">
                            <small>IMPROVEMENT SUGGESTIONS</small>
                            <ul>
                                ${suggestions.map(s => `<li>${escapeHtml(s)}</li>`).join("")}
                            </ul>
                        </div>
                    ` : ""}
                    ${followUp ? `
                        <div class="session-followup-box">
                            <small>FOLLOW-UP QUESTION</small>
                            <p>${escapeHtml(followUp)}</p>
                        </div>
                    ` : ""}
                </div>
                <button type="button" class="session-toggle-btn" onclick="toggleSessionDetails(${index}, this)">
                    View Feedback Details ▼
                </button>
            `;

            container.appendChild(div);
        });

    } catch (error) {
        console.error("Error loading history:", error);
        container.innerHTML = `
            <p class="muted">
                Could not connect to fetch history. Click Refresh to try again.
            </p>
        `;
    }
}

// Initial history load
loadHistory();