// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "PreviewLikePDFZoom",
    platforms: [
        .macOS(.v13)
    ],
    products: [
        .executable(name: "PreviewLikePDFZoomApp", targets: ["PreviewLikePDFZoomApp"]),
        .library(name: "PreviewLikePDFZoomKit", targets: ["PreviewLikePDFZoomKit"])
    ],
    dependencies: [],
    targets: [
        .target(
            name: "PreviewLikePDFZoomKit",
            dependencies: [],
            swiftSettings: [
                .define("SWIFT_PACKAGE")
            ]
        ),
        .executableTarget(
            name: "PreviewLikePDFZoomApp",
            dependencies: ["PreviewLikePDFZoomKit"],
            path: "Sources/PreviewLikePDFZoomApp"
        ),
        .testTarget(
            name: "PreviewLikePDFZoomKitTests",
            dependencies: ["PreviewLikePDFZoomKit"],
            resources: [
                .process("Resources")
            ],
            swiftSettings: [
                .define("SWIFT_PACKAGE")
            ]
        )
    ]
)
