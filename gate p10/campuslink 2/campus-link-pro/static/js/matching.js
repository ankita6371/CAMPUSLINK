document.addEventListener("DOMContentLoaded", function () {
    const table = document.getElementById("matching-table");
    const search = document.getElementById("candidate-search");
    const threshold = document.getElementById("minimum-score");
    const status = document.getElementById("match-status");
    const noResults = document.getElementById("no-results");
    const rows = table ? Array.from(table.querySelectorAll("tbody tr[data-score]")) : [];
    const exportButton = document.getElementById("export-results");

    function filterCandidates() {
        const query = (search?.value || "").trim().toLowerCase();
        const minimum = Number(threshold?.value || 0);
        let visible = 0;

        rows.forEach(function (row) {
            const searchableText = [
                row.dataset.candidate || "",
                row.dataset.skills || ""
            ].join(" ");
            const matchesName = searchableText.includes(query);
            const matchesScore = Number(row.dataset.score) >= minimum;
            row.classList.toggle("is-hidden", !matchesName || !matchesScore);
            if (matchesName && matchesScore) visible += 1;
        });

        if (noResults) noResults.hidden = rows.length === 0 || visible !== 0;
    }

    if (search) search.addEventListener("input", filterCandidates);
    if (threshold) threshold.addEventListener("change", filterCandidates);

    if (exportButton) {
        exportButton.addEventListener("click", function () {
            const visibleRows = rows.filter(function (row) {
                return !row.classList.contains("is-hidden");
            });
            if (!visibleRows.length) {
                if (status) status.textContent = "There are no matching candidates to export.";
                return;
            }
            const csvRows = [[
                "Rank", "Candidate", "Registration", "Branch", "CGPA",
                "Skills matched", "Skills to build", "Other unmet requirements",
                "Match score"
            ]];
            visibleRows.forEach(function (row) {
                const cells = row.querySelectorAll("td");
                csvRows.push([
                    cells[0].innerText.trim(),
                    cells[1].querySelector("strong")?.innerText.trim() || "",
                    cells[1].querySelector("small")?.innerText.trim() || "",
                    cells[2].innerText.trim(),
                    cells[3].innerText.trim(),
                    Array.from(cells[4].querySelectorAll(".skill-chip-matched"))
                        .map(function (chip) { return chip.innerText.trim(); })
                        .join("; "),
                    Array.from(cells[5].querySelectorAll(".skill-chip-gap"))
                        .map(function (chip) { return chip.innerText.trim(); })
                        .join("; "),
                    Array.from(cells[5].querySelectorAll(".requirement-gap-item"))
                        .map(function (item) { return item.innerText.trim(); })
                        .join("; "),
                    cells[6].innerText.replace(/\s+/g, " ").trim()
                ]);
            });
            const csv = csvRows.map(function (row) {
                return row.map(function (value) {
                    return '"' + String(value).replace(/"/g, '""') + '"';
                }).join(",");
            }).join("\r\n");
            const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
            const link = document.createElement("a");
            link.href = url;
            link.download = "campuslink-matching-results.csv";
            document.body.append(link);
            link.click();
            link.remove();
            URL.revokeObjectURL(url);
            if (status) status.textContent = "Visible matching results exported.";
        });
    }

    filterCandidates();
});
