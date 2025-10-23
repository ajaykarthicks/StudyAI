import PyPDF2
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.embeddings import OpenAIEmbeddings
from langchain.vectorstores import Chroma
from langchain.chains import ConversationalRetrievalChain
from langchain.llms import OpenAI

class PDFProcessor:
    def __init__(self):
        self.embeddings = OpenAIEmbeddings()
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200
        )
    
    def extract_text(self, pdf_file):
        reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            text += page.extract_text()
        return text
    
    def create_vector_store(self, text):
        chunks = self.text_splitter.split_text(text)
        vector_store = Chroma.from_texts(chunks, self.embeddings)
        return vector_store
    
    def create_qa_chain(self, vector_store):
        llm = OpenAI(temperature=0)
        qa_chain = ConversationalRetrievalChain.from_llm(
            llm, 
            vector_store.as_retriever(),
            return_source_documents=True
        )
        return qa_chain
