// Клиентские хелперы перевода: выбор формы множественного числа и подстановка
// параметров — те же правила, что в webapp/i18n.py (_plural_ru/ro/en),
// продублированы здесь, потому что выбор формы для чисел, которые меняются
// только в браузере (например, счётчик проблем Zabbix между опросами),
// не может ждать похода на сервер.
(function (global) {
  function pluralIdx(lang, n) {
    n = Math.abs(Math.trunc(n));
    if (lang === "ru") {
      if (n % 10 === 1 && n % 100 !== 11) return 0;
      if (n % 10 >= 2 && n % 10 <= 4 && !(n % 100 >= 12 && n % 100 <= 14))
        return 1;
      return 2;
    }
    if (lang === "ro") {                  // three CLDR forms, see _plural_ro
      if (n === 1) return 0;              // o cursă
      if (n === 0 || (n % 100 >= 1 && n % 100 <= 19)) return 1;  // 2 curse
      return 2;                           // 20 de curse — с предлогом
    }
    return n === 1 ? 0 : 1;               // en и по умолчанию
  }

  function fmt(str, params) {
    if (!params) return str;
    return str.replace(/\{(\w+)\}/g, (m, k) =>
      Object.prototype.hasOwnProperty.call(params, k) ? params[k] : m);
  }

  // I18N — плоские строки (client_catalog), I18NP — формы множественного
  // числа (client_plural_forms); оба словаря кладёт шаблон перед подключением
  // этого файла.
  global.tt = function (key, params) {
    var s = (global.I18N && global.I18N[key] != null) ? global.I18N[key] : key;
    return fmt(s, params);
  };
  global.ttn = function (key, n, params) {
    var forms = (global.I18NP && global.I18NP[key]) || [key];
    var idx = pluralIdx(global.LANG || "ru", n);
    var s = forms[Math.min(idx, forms.length - 1)];
    return fmt(s, Object.assign({ n: n }, params || {}));
  };
})(window);
