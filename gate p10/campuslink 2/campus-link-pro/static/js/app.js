document.addEventListener("DOMContentLoaded", function () {


    const menuButton = document.querySelector(".mobile-menu");
    const sidebar = document.querySelector(".sidebar");
    const notificationButton = document.getElementById("notificationButton");
    const notificationPanel = document.getElementById("notificationPanel");
    const notificationCount = document.getElementById("notificationCount");
    const markNotificationsRead = document.getElementById("markNotificationsRead");
    const notificationWrapper = document.querySelector(".notification-wrapper");
    const notificationFeedback = document.getElementById("notificationFeedback");
    const adminProfile = document.getElementById("adminProfile");
    const profileMenu = document.getElementById("profileMenu");

    if (menuButton && sidebar) {
        menuButton.addEventListener("click", function () {
            sidebar.classList.toggle("open");
        });
    }

    function closeNotifications() {
        if (!notificationButton || !notificationPanel) return;
        notificationPanel.hidden = true;
        notificationButton.setAttribute("aria-expanded", "false");
    }

    function closeProfileMenu() {
        if (!adminProfile || !profileMenu) return;
        profileMenu.hidden = true;
        adminProfile.setAttribute("aria-expanded", "false");
    }

    if (notificationButton && notificationPanel) {
        notificationButton.addEventListener("click", function () {
            const opening = notificationPanel.hidden;
            notificationPanel.hidden = !opening;
            notificationButton.setAttribute("aria-expanded", String(opening));
            closeProfileMenu();
        });
    }

    async function saveNotificationReceipts(signatures) {
        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || "";
        const response = await fetch("/notifications/read", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": csrfToken
            },
            body: JSON.stringify({ signatures: signatures })
        });
        const result = await response.json();
        if (!response.ok) {
            throw new Error(result.error || "Unable to update notifications.");
        }
    }

    if (markNotificationsRead && notificationCount && notificationButton) {
        markNotificationsRead.disabled = Number(notificationCount.dataset.count) === 0;
        markNotificationsRead.addEventListener("click", async function () {
            let signatures;
            try {
                signatures = JSON.parse(notificationCount.dataset.signatures || "[]");
                await saveNotificationReceipts(signatures);
                window.location.reload();
            } catch (error) {
                if (notificationFeedback) {
                    notificationFeedback.textContent = error.message || "Unable to update notifications.";
                    notificationFeedback.classList.add("has-error");
                }
            }
        });
    }

    document.querySelectorAll(".notification-item[data-notification-signature]")
        .forEach(function (item) {
            item.addEventListener("click", async function (event) {
                event.preventDefault();
                const destination = item.href;
                try {
                    await saveNotificationReceipts([item.dataset.notificationSignature]);
                    window.location.assign(destination);
                } catch (error) {
                    if (notificationFeedback) {
                        notificationFeedback.textContent = error.message || "Unable to update this notification.";
                        notificationFeedback.classList.add("has-error");
                    }
                }
            });
        });

    if (adminProfile && profileMenu) {
        function toggleProfileMenu() {
            const opening = profileMenu.hidden;
            profileMenu.hidden = !opening;
            adminProfile.setAttribute("aria-expanded", String(opening));
            closeNotifications();
        }

        adminProfile.addEventListener("click", toggleProfileMenu);
        adminProfile.addEventListener("keydown", function (event) {
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                toggleProfileMenu();
            }
        });
    }

    document.addEventListener("click", function (event) {
        if (notificationWrapper && !notificationWrapper.contains(event.target)) {
            closeNotifications();
        }
        if (
            adminProfile &&
            profileMenu &&
            !adminProfile.contains(event.target) &&
            !profileMenu.contains(event.target)
        ) {
            closeProfileMenu();
        }
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") {
            closeNotifications();
            closeProfileMenu();
        }
    });



    const currentPath = window.location.pathname;

    document.querySelectorAll(".nav-item").forEach(function (link) {

        const href = link.getAttribute("href");

        if (
            href &&
            href !== "/" &&
            currentPath === href
        ) {
            link.classList.add("active");
        }

    });



    document.addEventListener("click", function (event) {

        if (!sidebar || !menuButton) {
            return;
        }

        const clickedInsideSidebar = sidebar.contains(event.target);
        const clickedMenuButton = menuButton.contains(event.target);

        if (
            sidebar.classList.contains("open") &&
            !clickedInsideSidebar &&
            !clickedMenuButton
        ) {
            sidebar.classList.remove("open");
        }

    });



    document.addEventListener("keydown", function (event) {

        if (
            (event.ctrlKey || event.metaKey) &&
            event.key.toLowerCase() === "k"
        ) {

            event.preventDefault();

            const searchInput =
                document.querySelector(".topbar-search input");

            if (searchInput) {
                searchInput.focus();
            }

        }

    });



    const globalSearch = document.querySelector(".topbar-search input");
    const studentSearch = document.getElementById("studentSearch");

    if (globalSearch) {
        const query = new URLSearchParams(window.location.search).get("search") || "";

        if (studentSearch) {
            globalSearch.value = studentSearch.value || query;

            if (query) {
                studentSearch.value = query;
                studentSearch.dispatchEvent(new Event("input", { bubbles: true }));
            }

            globalSearch.addEventListener("input", function () {
                studentSearch.value = globalSearch.value;
                studentSearch.dispatchEvent(new Event("input", { bubbles: true }));
            });
        }

        globalSearch.addEventListener("keydown", function (event) {
            if (event.key !== "Enter") {
                return;
            }

            event.preventDefault();
            const value = globalSearch.value.trim();

            if (currentPath === "/students" && studentSearch) {
                studentSearch.value = value;
                studentSearch.dispatchEvent(new Event("input", { bubbles: true }));
                return;
            }

            if (value) {
                window.location.href = "/students?search=" + encodeURIComponent(value);
            }
        });
    }

});