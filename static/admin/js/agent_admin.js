(function ($) {
    $(document).ready(function () {
        var deptField = $('#id_department_obj');
        var stockRow = $('.field-stock');

        function toggleStockField() {
            var selectedText = deptField.find('option:selected').text();
            // "영업지원본부", "기획실", "재무관리실" 문구가 포함되어 있으면 숨김
            if (selectedText.includes('영업지원본부') || selectedText.includes('기획실') || selectedText.includes('재무관리실')) {
                stockRow.hide();
            } else {
                stockRow.show();
            }
        }

        // 이벤트 리스너 등록
        deptField.change(toggleStockField);

        // 초기 로드 시 실행
        toggleStockField();
    });
})(django.jQuery);
