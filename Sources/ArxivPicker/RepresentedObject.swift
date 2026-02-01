import AppKit
import ObjectiveC.runtime

private var representedObjectKey: UInt8 = 0

// NSView doesn't provide representedObject like NSMenuItem does.
// Add a lightweight storage slot for controls that need to carry model data.
extension NSView {
    var representedObject: Any? {
        get {
            objc_getAssociatedObject(self, &representedObjectKey)
        }
        set {
            objc_setAssociatedObject(self, &representedObjectKey, newValue, .OBJC_ASSOCIATION_RETAIN_NONATOMIC)
        }
    }
}
