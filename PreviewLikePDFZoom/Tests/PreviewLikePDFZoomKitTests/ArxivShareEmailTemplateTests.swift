import XCTest
@testable import PreviewLikePDFZoomKit

final class ArxivShareEmailTemplateTests: XCTestCase {
    func testBodyUsesThereWhenUnknown() {
        XCTAssertEqual(
            ArxivShareEmailTemplate.body(recipientName: nil, arxivAbsURL: "https://arxiv.org/abs/1234.56789"),
            "Hey there,\n\nhttps://arxiv.org/abs/1234.56789"
        )
    }

    func testBodyUsesTrimmedRecipientName() {
        XCTAssertEqual(
            ArxivShareEmailTemplate.body(recipientName: "  Alice  ", arxivAbsURL: "https://arxiv.org/abs/9999.00001"),
            "Hey Alice,\n\nhttps://arxiv.org/abs/9999.00001"
        )
    }
}
