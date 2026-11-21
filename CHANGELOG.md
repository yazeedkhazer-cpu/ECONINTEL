# CHANGELOG

## v1.2 — Ready-to-deploy online data infrastructure (21 Nov 2026)
- Retained original ECONINTEL v1.1 Arabic interface and all 34 labor-market indicators.
- Added robust no-key BLS Public API v1 fallback and registered v2 support.
- Added derived 3/12-month NFP and long-term unemployment share from official series.
- Added optional FRED pipeline for weekly claims, quarterly ECI/productivity/ULC and Sahm indicator.
- Added server-side validated merge, source provenance and capture-time snapshots.
- Added hourly weekday / weekend scheduled GitHub Pages deployment.
- Added client-side JSON polling on load, every 5 minutes, and manual refresh button.
- Added live/reference distinction in the UI, with per-indicator capture times.
- Expanded offline unit tests from six to eleven.
- Four indicators still require separate approved data feeds; not claimed live.

---

# Changelog

## 1.1.0 — 2026-11-17

- إضافة توثيق واضح لكل مؤشر: نسخة مرجعية، مستوردة، محدّثة عبر BLS، أو قديمة.
- واجهة جودة بيانات تعرض عدد المؤشرات حسب مصدرها، مع مراقبة تقادم فترة المرجع.
- تحديث محرك BLS ليشمل المشاركة بالفئة الأساسية، العمالة المؤقتة، التعيينات والاستقالات والتسريحات، ونسبة الشواغر للعاطلين في الفترة نفسها.
- إصلاح إنشاء مجلد `data/` وكتابة ملف التحديث عند نجاحه، وعدم نشر بيانات ناقصة.
- إضافة اختبارات وحدات لحسابات البيانات، وفحص مرور الأشهر دون سد فجواتها.
- إصلاح تباين النصوص داخل بطاقات المؤشرات، وحماية تصدير CSV من مدخلات النص التنفيذية.
- تحسين تسميات البطاقات والتنبيه إلى أن القطاعات والمواعيد المعروضة مرجعية لا يتم تحديثها آليًا.
- إعداد نسخة HTML مفردة تعمل محليًا، مع ملفات مصدر منظمة وجاهزة للاستضافة.

### Limitations

- لم يتم الاتصال بواجهة BLS من بيئة البناء؛ اختبار التحديث الحي بعد الاستضافة/على جهاز متصل بالإنترنت ما زال مطلوبًا.
- مؤشرات أخرى غير BLS والقطاعات وSahm وClaims لا تزال بحاجة إلى مصادر وتحديث خاص بها.
- لم يُنشر الموقع على دومين عام.
