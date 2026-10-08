(() => {
    const root = document.getElementById("ai-practice");
    if (!root) return;

    const context = window.interviewPracticeContext || {};
    const questions = [
        { category: "Introduction", text: "Please introduce yourself and tell me what interests you about the {role} opportunity at {company}." },
        { category: "Motivation", text: "Why are you interested in joining {company}, and what would you bring to the {role} position?" },
        { category: "Experience", text: "Tell me about a project or piece of work that you are proud of. What was your contribution and what was the result?" },
        { category: "Problem solving", text: "Describe a challenging problem you faced. How did you approach it, and what did you learn?" },
        { category: "Teamwork", text: "Tell me about a time you worked with others to achieve a goal. How did you handle different ideas or approaches?" },
        { category: "Adaptability", text: "Describe a time you had to learn something new quickly. What steps did you take?" },
        { category: "Strengths", text: "Which of your strengths would be most useful in this role? Please share a specific example." },
        { category: "Growth", text: "What is one skill you are currently working to improve, and how are you developing it?" },
        { category: "Ownership", text: "Tell me about a time you took initiative without being asked. What happened as a result?" },
        { category: "Communication", text: "Describe a situation where you had to explain a complex idea to someone unfamiliar with it." },
        { category: "Resilience", text: "Tell me about a setback you experienced. How did you respond and move forward?" },
        { category: "Priorities", text: "How do you prioritize when you have several important deadlines at the same time?" },
        { category: "Role readiness", text: "What do you think will be the most important contribution you can make in your first few months as a {role}?" },
        { category: "Career goals", text: "What kind of work would you like to be doing three years from now, and how does this opportunity fit?" },
        { category: "Closing", text: "Is there anything else about your experience or interests that you would like me to know?" },
        { category: "Technical thinking", text: "Walk me through how you would break down an unfamiliar technical problem before choosing a solution." },
        { category: "Technical thinking", text: "How do you check the quality and reliability of work before you consider it complete?" },
        { category: "Technical thinking", text: "Tell me about a technical concept you learned recently. How would you explain it to a teammate?" },
        { category: "Technical thinking", text: "If your first solution to a technical problem did not work, how would you decide what to try next?" },
        { category: "Project work", text: "How did you decide which tools or approach to use in a recent project, and what trade-offs did you consider?" },
        { category: "Feedback", text: "Tell me about a time you received constructive feedback. How did you apply it?" },
        { category: "Conflict", text: "Describe a professional disagreement and how you worked toward a constructive outcome." },
        { category: "Customer focus", text: "How would you respond if a stakeholder was unhappy with a result that met the original requirements?" },
        { category: "Learning", text: "What would you do if you were assigned a task in an area where you had limited experience?" }
    ];
    const questionCount = 6;
    const video = document.getElementById("candidate-video");
    const placeholder = document.getElementById("camera-placeholder");
    const indicator = document.getElementById("camera-indicator");
    const mediaMessage = document.getElementById("media-message");
    const startButton = document.getElementById("start-practice");
    const textOnlyButton = document.getElementById("continue-text-only");
    const endButton = document.getElementById("end-practice");
    const questionText = document.getElementById("question-text");
    const questionProgress = document.getElementById("question-progress");
    const answerInput = document.getElementById("answer-input");
    const nextButton = document.getElementById("next-question");
    const dictateButton = document.getElementById("dictate-answer");
    const speechSupport = document.getElementById("speech-support");
    const resultsPanel = document.getElementById("practice-results");
    const questionCard = document.getElementById("question-card");
    const recognitionConstructor = window.SpeechRecognition || window.webkitSpeechRecognition;
    let stream = null;
    let recognition = null;
    let sessionQuestions = [];
    let answers = [];
    let questionIndex = 0;
    let previousSet = "";
    let sessionStarted = false;
    let isDictating = false;

    function stopDictation() {
        if (recognition && isDictating) recognition.stop();
        isDictating = false;
        dictateButton.innerHTML = '<i class="fa-solid fa-microphone"></i> Dictate answer';
        dictateButton.classList.remove("is-listening");
    }

    function stopMedia() {
        stopDictation();
        if (stream) {
            stream.getTracks().forEach((track) => track.stop());
            stream = null;
        }
        video.srcObject = null;
        video.hidden = true;
        placeholder.hidden = false;
        document.getElementById("camera-name-tag").hidden = true;
        indicator.innerHTML = '<i class="fa-solid fa-circle"></i> Camera off';
        indicator.classList.remove("is-live");
    }

    function shuffle(items) {
        const result = items.slice();
        for (let i = result.length - 1; i > 0; i -= 1) {
            const j = Math.floor(Math.random() * (i + 1));
            [result[i], result[j]] = [result[j], result[i]];
        }
        return result;
    }

    function chooseQuestions() {
        let selection = shuffle(questions).slice(0, questionCount);
        let signature = selection.map((item) => item.text).sort().join("|");
        let attempts = 0;
        while (signature === previousSet && attempts < 5) {
            selection = shuffle(questions).slice(0, questionCount);
            signature = selection.map((item) => item.text).sort().join("|");
            attempts += 1;
        }
        previousSet = signature;
        return selection.map((item) => ({
            category: item.category,
            text: item.text
                .replaceAll("{student}", context.student || "there")
                .replaceAll("{company}", context.company || "the company")
                .replaceAll("{role}", context.role || "role")
        }));
    }

    function askCurrentQuestion() {
        const question = sessionQuestions[questionIndex];
        questionText.textContent = question.text;
        questionProgress.textContent = `Question ${questionIndex + 1} of ${sessionQuestions.length} · ${question.category}`;
        nextButton.innerHTML = questionIndex === sessionQuestions.length - 1
            ? 'Finish session <i class="fa-solid fa-check"></i>'
            : 'Next question <i class="fa-solid fa-arrow-right"></i>';
        answerInput.value = "";
        answerInput.focus();
        if ("speechSynthesis" in window) {
            window.speechSynthesis.cancel();
            window.speechSynthesis.speak(new SpeechSynthesisUtterance(question.text));
        }
    }

    function startQuestions() {
        sessionQuestions = chooseQuestions();
        answers = [];
        questionIndex = 0;
        sessionStarted = true;
        startButton.hidden = true;
        textOnlyButton.hidden = true;
        endButton.hidden = false;
        answerInput.disabled = false;
        nextButton.disabled = false;
        dictateButton.disabled = !recognitionConstructor;
        resultsPanel.hidden = true;
        questionCard.hidden = false;
        if (recognitionConstructor) {
            speechSupport.textContent = "Speech-to-text is handled by your browser; typed answers are also available.";
        } else {
            speechSupport.textContent = "Speech-to-text is not available in this browser. You can type your answer.";
        }
        askCurrentQuestion();
        mediaMessage.textContent = stream ? "Camera and microphone are ready." : "Practice is running in text-only mode.";
    }

    function feedbackFor(answer) {
        const words = answer.trim().split(/\s+/).filter(Boolean);
        const wordCount = answer.trim() ? words.length : 0;
        const lower = answer.toLowerCase();
        const hasStructure = /\b(situation|task|action|result|first|then|finally|because)\b/.test(lower);
        const hasEvidence = /\b\d+(?:\.\d+)?%?\b/.test(answer) || /\b(reduced|increased|improved|completed|delivered|saved|built|launched)\b/.test(lower);
        const notes = [];
        if (wordCount < 20) notes.push("Add more detail so the interviewer can understand your approach.");
        else notes.push("Good detail: your answer gives the interviewer useful context.");
        if (hasStructure) notes.push("A clear sequence or situation-action-result structure is present.");
        else notes.push("Try organizing the example into the situation, your action, and the result.");
        if (hasEvidence) notes.push("You included an outcome or concrete evidence; explain your personal contribution too.");
        else notes.push("Where possible, include a specific outcome or measurable result.");
        return { wordCount, notes };
    }

    function showResults() {
        const feedback = answers.map((answer, index) => ({
            question: sessionQuestions[index].text,
            ...feedbackFor(answer)
        }));
        const averageWords = feedback.length
            ? Math.round(feedback.reduce((total, item) => total + item.wordCount, 0) / feedback.length)
            : 0;
        document.getElementById("results-summary").innerHTML =
            `<strong>${answers.length} / ${sessionQuestions.length}</strong><span>questions answered</span><strong>${averageWords}</strong><span>average words per answer</span>`;
        const feedbackList = document.getElementById("answer-feedback");
        feedbackList.replaceChildren();
        feedback.forEach((item, index) => {
            const card = document.createElement("article");
            card.className = "answer-feedback-item";
            const heading = document.createElement("h3");
            heading.textContent = `Question ${index + 1}`;
            const prompt = document.createElement("p");
            prompt.textContent = item.question;
            const noteList = document.createElement("ul");
            item.notes.forEach((note) => {
                const li = document.createElement("li");
                li.textContent = note;
                noteList.append(li);
            });
            card.append(heading, prompt, noteList);
            feedbackList.append(card);
        });
        questionCard.hidden = true;
        resultsPanel.hidden = false;
        endButton.hidden = true;
        startButton.hidden = false;
        startButton.innerHTML = '<i class="fa-solid fa-rotate-right"></i> Start new session';
        sessionStarted = false;
        stopMedia();
        mediaMessage.textContent = "Session complete. Your camera and microphone are off.";
        resultsPanel.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    function saveAnswerAndContinue() {
        stopDictation();
        answers[questionIndex] = answerInput.value.trim();
        if (questionIndex === sessionQuestions.length - 1) {
            showResults();
            return;
        }
        questionIndex += 1;
        askCurrentQuestion();
    }

    startButton.addEventListener("click", async () => {
        if (sessionStarted) {
            startQuestions();
            return;
        }
        startButton.disabled = true;
        mediaMessage.textContent = "Requesting camera and microphone access…";
        textOnlyButton.hidden = true;
        try {
            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                throw new Error("Camera access requires a supported browser and a secure connection such as localhost.");
            }
            stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
            video.srcObject = stream;
            video.hidden = false;
            placeholder.hidden = true;
            document.getElementById("camera-name-tag").hidden = false;
            indicator.innerHTML = '<i class="fa-solid fa-circle"></i> Camera on';
            indicator.classList.add("is-live");
            mediaMessage.textContent = "Camera and microphone are ready.";
            startQuestions();
        } catch (error) {
            mediaMessage.textContent = `${error.message || "Camera or microphone permission was not granted."} You can still practice with typed answers.`;
            textOnlyButton.hidden = false;
        } finally {
            startButton.disabled = false;
        }
    });

    textOnlyButton.addEventListener("click", startQuestions);
    endButton.addEventListener("click", () => {
        if ("speechSynthesis" in window) window.speechSynthesis.cancel();
        stopDictation();
        stopMedia();
        sessionStarted = false;
        questionCard.hidden = true;
        resultsPanel.hidden = true;
        startButton.hidden = false;
        startButton.innerHTML = '<i class="fa-solid fa-play"></i> Start practice';
        textOnlyButton.hidden = true;
        endButton.hidden = true;
        mediaMessage.textContent = "Session ended. Your camera and microphone are off.";
    });
    nextButton.addEventListener("click", saveAnswerAndContinue);
    dictateButton.addEventListener("click", () => {
        if (!recognitionConstructor) return;
        if (isDictating) {
            recognition.stop();
            isDictating = false;
            dictateButton.innerHTML = '<i class="fa-solid fa-microphone"></i> Dictate answer';
            dictateButton.classList.remove("is-listening");
            return;
        }
        recognition = new recognitionConstructor();
        recognition.lang = navigator.language || "en-US";
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.onresult = (event) => {
            let finalText = "";
            let interimText = "";
            for (let i = event.resultIndex; i < event.results.length; i += 1) {
                const transcript = event.results[i][0].transcript;
                if (event.results[i].isFinal) finalText += transcript + " ";
                else interimText += transcript;
            }
            if (finalText) answerInput.value = `${answerInput.value.trimEnd()} ${finalText}`.trimStart();
            if (interimText) speechSupport.textContent = `Listening: ${interimText}`;
        };
        recognition.onerror = (event) => {
            speechSupport.textContent = `Speech recognition: ${event.error}. You can continue typing.`;
        };
        recognition.onend = () => {
            isDictating = false;
            dictateButton.innerHTML = '<i class="fa-solid fa-microphone"></i> Dictate answer';
            dictateButton.classList.remove("is-listening");
            if (speechSupport.textContent.startsWith("Listening:")) {
                speechSupport.textContent = "Speech-to-text stopped. Review the transcript and edit if needed.";
            }
        };
        try {
            recognition.start();
            isDictating = true;
            dictateButton.innerHTML = '<i class="fa-solid fa-microphone-lines"></i> Stop dictation';
            dictateButton.classList.add("is-listening");
            speechSupport.textContent = "Listening…";
        } catch (error) {
            speechSupport.textContent = `Could not start speech recognition: ${error.message}. Type your answer instead.`;
        }
    });
    document.getElementById("practice-again").addEventListener("click", () => {
        resultsPanel.hidden = true;
        startQuestions();
        root.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    window.addEventListener("pagehide", stopMedia);
})();
