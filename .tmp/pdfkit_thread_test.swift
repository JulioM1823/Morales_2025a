import Foundation
import PDFKit
import CoreGraphics

let tmp = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("pdfkit_thread_test_\(UUID().uuidString).pdf")

var box = CGRect(x: 0, y: 0, width: 200, height: 200)
guard let consumer = CGDataConsumer(url: tmp as CFURL) else {
  print("no consumer")
  exit(1)
}
guard let ctx = CGContext(consumer: consumer, mediaBox: &box, nil) else {
  print("no context")
  exit(1)
}
ctx.beginPDFPage(nil)
ctx.endPDFPage()
ctx.closePDF()

let sem = DispatchSemaphore(value: 0)
var bgOK = false
DispatchQueue.global(qos: .userInitiated).async {
  bgOK = (PDFDocument(url: tmp) != nil)
  sem.signal()
}
_ = sem.wait(timeout: .now() + 5)
let mainOK = (PDFDocument(url: tmp) != nil)
print("bgOK=\(bgOK) mainOK=\(mainOK) url=\(tmp.path)")
try? FileManager.default.removeItem(at: tmp)
