// Mobile nav toggle
const burger = document.getElementById('burger');
const nav = document.getElementById('nav');
if (burger && nav) {
  burger.addEventListener('click', () => {
    const isOpen = nav.classList.toggle('is-open');
    burger.setAttribute('aria-expanded', String(isOpen));
  });
  nav.querySelectorAll('a').forEach((link) => {
    link.addEventListener('click', () => {
      nav.classList.remove('is-open');
      burger.setAttribute('aria-expanded', 'false');
    });
  });
}

// Apartment tabs
const tabButtons = document.querySelectorAll('.tabs__btn');
const tabPanels = document.querySelectorAll('.tabs__panel');
tabButtons.forEach((btn) => {
  btn.addEventListener('click', () => {
    tabButtons.forEach((b) => b.classList.remove('is-active'));
    tabPanels.forEach((p) => p.classList.remove('is-active'));
    btn.classList.add('is-active');
    document.getElementById(btn.dataset.tab).classList.add('is-active');
  });
});

// FAQ accordion
document.querySelectorAll('.faq__item').forEach((item) => {
  const q = item.querySelector('.faq__q');
  q.addEventListener('click', () => {
    const wasOpen = item.classList.contains('is-open');
    document.querySelectorAll('.faq__item').forEach((i) => i.classList.remove('is-open'));
    if (!wasOpen) item.classList.add('is-open');
  });
});

// Lead form (front-end only — no CRM/backend wired up yet)
const leadForm = document.getElementById('leadForm');
const formNote = document.getElementById('formNote');
if (leadForm) {
  leadForm.addEventListener('submit', (e) => {
    e.preventDefault();
    if (!leadForm.checkValidity()) {
      formNote.textContent = 'Заполните имя и телефон.';
      return;
    }
    formNote.textContent = 'Спасибо! Заявка принята — мы свяжемся с вами в ближайшее время.';
    leadForm.reset();
  });
}

// Header shrink on scroll
const header = document.getElementById('header');
if (header) {
  window.addEventListener('scroll', () => {
    header.style.boxShadow = window.scrollY > 8 ? '0 4px 20px rgba(20,48,74,.08)' : 'none';
  });
}
