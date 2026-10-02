"use strict";

/*
 * Deal Hunter — static loader and card renderer (M2-B + M2-C).
 *
 * Loads ./deals.json, validates the minimal document shape and
 * materializes one card per deal inside #deals-list.
 *
 * The frontend only presents values that arrive in the document:
 * no scoring, no recalculation, no approval rules, no external
 * requests beyond ./deals.json (and optional https images from
 * the document itself).
 *
 * Security: local script only. Every value enters the DOM via
 * textContent or setAttribute — never through HTML strings.
 */

(function () {
    var loadingState = document.getElementById("state-loading");
    var errorState = document.getElementById("state-error");
    var emptyState = document.getElementById("state-empty");
    var dealsList = document.getElementById("deals-list");

    function setState(name) {
        loadingState.hidden = name !== "loading";
        errorState.hidden = name !== "error";
        emptyState.hidden = name !== "empty";
        dealsList.hidden = name !== "ready";
    }

    function showLoading() {
        setState("loading");
    }

    function showError() {
        setState("error");
    }

    function showEmpty() {
        setState("empty");
    }

    function showReady() {
        setState("ready");
    }

    function isValidDocument(data) {
        if (
            typeof data !== "object" ||
            data === null ||
            Array.isArray(data)
        ) {
            return false;
        }

        if (data.version !== 1) {
            return false;
        }

        if (!Array.isArray(data.deals)) {
            return false;
        }

        return true;
    }

    function isHttpsUrl(value) {
        return (
            typeof value === "string" &&
            /^https:\/\//.test(value)
        );
    }

    function formatPrice(amount, currency) {
        return new Intl.NumberFormat("en-US", {
            style: "currency",
            currency: currency
        }).format(amount);
    }

    function formatDate(value) {
        return new Intl.DateTimeFormat("en-US", {
            dateStyle: "medium",
            timeZone: "UTC"
        }).format(new Date(value));
    }

    function appendHistory(card, deal) {
        if (
            !Array.isArray(deal.history) ||
            deal.history.length === 0
        ) {
            return;
        }

        var points = deal.history.slice();

        points.sort(function (left, right) {
            if (left.date === right.date) {
                return 0;
            }

            return left.date < right.date ? 1 : -1;
        });

        var recent = points.slice(0, 5);

        var section = document.createElement("section");

        section.className = "deal-history";
        section.setAttribute("aria-label", "Price history");

        var heading = document.createElement("h4");

        heading.textContent = "Price history";

        section.append(heading);

        var list = document.createElement("ul");

        recent.forEach(function (point) {
            var item = document.createElement("li");

            var when = document.createElement("time");

            when.setAttribute("datetime", point.date);
            when.textContent = formatDate(point.date);

            var amount = document.createElement("span");

            amount.className = "history-price";
            amount.textContent = formatPrice(point.price, deal.currency);

            item.append(when);
            item.append(amount);

            list.append(item);
        });

        section.append(list);

        card.append(section);
    }

    function appendBadge(parent, className, text) {
        var badge = document.createElement("span");

        badge.className = className;
        badge.textContent = text;

        parent.append(badge);
    }

    function appendBadges(card, deal) {
        var entries = [];

        if (deal.discount_pct !== null) {
            entries.push([
                "badge badge-discount",
                deal.discount_pct + "%"
            ]);
        }

        if (deal.score !== null) {
            entries.push([
                "badge badge-score",
                "Score " + deal.score
            ]);
        }

        if (deal.label !== null) {
            entries.push(["badge", deal.label]);
        }

        if (entries.length === 0) {
            return;
        }

        var container = document.createElement("div");

        container.className = "deal-badges";

        entries.forEach(function (entry) {
            appendBadge(container, entry[0], entry[1]);
        });

        card.append(container);
    }

    function renderDeal(deal) {
        var card = document.createElement("li");

        card.className = "deal deal-card";

        var titleText = deal.title || "Product " + deal.id;

        var imageBox = document.createElement("div");

        imageBox.className = "deal-image";

        if (isHttpsUrl(deal.image)) {
            var picture = document.createElement("img");

            picture.setAttribute("src", deal.image);
            picture.setAttribute("alt", titleText);
            picture.setAttribute("loading", "lazy");

            imageBox.append(picture);
        } else {
            imageBox.textContent = "🔥";
        }

        card.append(imageBox);

        var title = document.createElement("h3");

        title.className = "deal-title";
        title.textContent = titleText;

        card.append(title);

        var priceRow = document.createElement("div");

        priceRow.className = "deal-price-row";

        var current = document.createElement("span");

        current.className = "price-current";
        current.textContent = formatPrice(
            deal.price,
            deal.currency
        );

        priceRow.append(current);

        if (
            typeof deal.previous_price === "number" &&
            deal.previous_price > deal.price
        ) {
            var before = document.createElement("s");

            before.className = "price-before";
            before.textContent = formatPrice(
                deal.previous_price,
                deal.currency
            );

            priceRow.append(before);
        }

        card.append(priceRow);

        appendBadges(card, deal);

        var date = document.createElement("time");

        date.className = "deal-date";
        date.setAttribute("datetime", deal.published_at);
        date.textContent = formatDate(deal.published_at);

        card.append(date);

        appendHistory(card, deal);

        if (isHttpsUrl(deal.url)) {
            var link = document.createElement("a");

            link.className = "deal-cta";
            link.setAttribute("href", deal.url);
            link.setAttribute("target", "_blank");
            link.setAttribute(
                "rel",
                "sponsored nofollow noopener"
            );
            link.textContent = "View deal";

            card.append(link);
        }

        return card;
    }

    function renderDeals(deals) {
        while (dealsList.firstChild) {
            dealsList.removeChild(dealsList.firstChild);
        }

        deals.forEach(function (deal) {
            dealsList.append(renderDeal(deal));
        });
    }

    function handleDocument(data) {
        if (!isValidDocument(data)) {
            throw new Error("invalid deals document");
        }

        if (data.deals.length === 0) {
            showEmpty();

            return;
        }

        renderDeals(data.deals);
        showReady();
    }

    function load() {
        showLoading();

        fetch("./deals.json", { cache: "no-cache" })
            .then(function (response) {
                if (!response.ok) {
                    throw new Error(
                        "deals request failed"
                    );
                }

                return response.json();
            })
            .then(handleDocument)
            .catch(function (error) {
                console.error("deals load failed:", error.message);

                showError();
            });
    }

    load();
})();
