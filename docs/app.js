const deals = [
  {
    emoji: "🎧",
    title: "Wireless Noise Cancelling Headphones",
    price: "$79.99",
    oldPrice: "$119.99",
    discount: "-33%",
    score: 94,
    confidence: "HIGH",
    history: "30-day avg. $119.99"
  },
  {
    emoji: "⌨️",
    title: "Mechanical Gaming Keyboard",
    price: "$49.99",
    oldPrice: "$79.99",
    discount: "-38%",
    score: 91,
    confidence: "HIGH",
    history: "30-day avg. $72.50"
  },
  {
    emoji: "🔌",
    title: "65W USB-C GaN Fast Charger",
    price: "$24.99",
    oldPrice: "$39.99",
    discount: "-38%",
    score: 87,
    confidence: "MEDIUM",
    history: "30-day avg. $34.99"
  },
  {
    emoji: "🖥️",
    title: "27-inch QHD Computer Monitor",
    price: "$179.99",
    oldPrice: "$249.99",
    discount: "-28%",
    score: 86,
    confidence: "HIGH",
    history: "30-day avg. $229.99"
  },
  {
    emoji: "🖱️",
    title: "Ergonomic Wireless Mouse",
    price: "$29.99",
    oldPrice: "$44.99",
    discount: "-33%",
    score: 84,
    confidence: "HIGH",
    history: "30-day avg. $39.99"
  },
  {
    emoji: "💾",
    title: "1TB Portable External SSD",
    price: "$64.99",
    oldPrice: "$99.99",
    discount: "-35%",
    score: 82,
    confidence: "MEDIUM",
    history: "30-day avg. $89.99"
  }
];

const grid = document.getElementById("deal-grid");

grid.innerHTML = deals.map(deal => `
  <article class="deal-card">
    <div class="product-image">${deal.emoji}</div>
    <div class="deal-content">
      <span class="badge">🔥 ${deal.score}/100 DEAL</span>
      <div class="deal-title">${deal.title}</div>

      <div class="price-row">
        <span class="current-price">${deal.price}</span>
        <span class="old-price">${deal.oldPrice}</span>
      </div>

      <div class="discount">${deal.discount} vs. typical price</div>

      <div class="deal-meta">
        <span>📉 ${deal.history}</span>
        <span>🛡️ ${deal.confidence}</span>
      </div>

      <a class="deal-button" href="#" onclick="return false;">
        View Deal on Amazon →
      </a>
    </div>
  </article>
`).join("");
