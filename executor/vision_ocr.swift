import Foundation
import Vision

// Local-only OCR. Image bytes arrive on stdin and are never written to disk.
do {
    let data = FileHandle.standardInput.readDataToEndOfFile()
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.recognitionLanguages = ["zh-Hans", "en-US"]
    request.usesLanguageCorrection = false
    let handler = VNImageRequestHandler(data: data, options: [:])
    try handler.perform([request])
    let rows: [[String: Any]] = (request.results ?? []).compactMap { observation in
        guard let value = observation.topCandidates(1).first else { return nil }
        let box = observation.boundingBox
        return ["text": value.string, "confidence": value.confidence,
                "x": box.minX, "y": 1 - box.maxY,
                "width": box.width, "height": box.height]
    }
    let result = try JSONSerialization.data(withJSONObject: rows, options: [.sortedKeys])
    FileHandle.standardOutput.write(result)
} catch {
    FileHandle.standardError.write(Data("Local text recognition unavailable".utf8))
    exit(1)
}
