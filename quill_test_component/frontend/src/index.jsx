import React, { useEffect, useRef } from "react"
import Quill from "quill"
import "quill/dist/quill.snow.css"

export default function QuillTest({ value, apply_replace, streamlit }) {
  const el = useRef(null)
  const quill = useRef(null)

  // init
  useEffect(() => {
    quill.current = new Quill(el.current, { theme: "snow" })

    quill.current.root.innerHTML = value

    quill.current.on("text-change", () => {
      streamlit.setComponentValue({
        type: "content",
        html: quill.current.root.innerHTML,
      })
    })

    quill.current.root.addEventListener("contextmenu", (e) => {
      e.preventDefault()
      const range = quill.current.getSelection()
      if (!range || range.length === 0) return

      streamlit.setComponentValue({
        type: "replace_request",
        range,
        text: quill.current.getText(range.index, range.length),
      })
    })
  }, [])

  // 🔥 APPLY REPLACE — КЛЮЧЕВОЕ
  useEffect(() => {
    if (!apply_replace || !quill.current) return

    const { range, text } = apply_replace

    quill.current.deleteText(range.index, range.length, "user")
    quill.current.insertText(range.index, text, "user")
  }, [apply_replace])
  }, [apply_replace])

  return <div ref={el} style={{ height: 300 }} />
}
